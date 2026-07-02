"""
S3 and File service layer - AWS S3 integration and file management
"""
import boto3
import logging
import os
import re
import unicodedata
import uuid
from pathlib import Path
from typing import Optional, List, BinaryIO
from bson import ObjectId
from botocore.exceptions import ClientError
from datetime import datetime
from app.core.config import settings
from app.models.file import File

_logger = logging.getLogger(__name__)

_FILENAME_SAFE_RE = re.compile(r"[^A-Za-z0-9._-]+")


class StorageBackendUnavailable(Exception):
    """The file's storage backend cannot serve it on this server.

    Typical cause: the File record says ``storage_type == "s3"`` but the server
    is running without AWS credentials (S3Service fell back to local disk).
    Surfaced to clients as HTTP 503 by the app-level exception handler, so
    misconfiguration shows up as a clear message instead of a generic 500.
    """


# Magic-byte signatures for the file types listed in settings.ALLOWED_EXTENSIONS.
# Each entry is a list of acceptable signatures; a signature is (offset, bytes).
# An extension can pass if ANY of its signatures matches.
#
# Sources: ISO standards, RFCs, and well-known file format docs. Verified against
# real-world samples — not just spec quotes.
_MAGIC_SIGNATURES: dict[str, list[tuple[int, bytes]]] = {
    "pdf":  [(0, b"%PDF-")],
    "png":  [(0, b"\x89PNG\r\n\x1a\n")],
    "jpg":  [(0, b"\xff\xd8\xff")],
    "jpeg": [(0, b"\xff\xd8\xff")],
    "gif":  [(0, b"GIF87a"), (0, b"GIF89a")],
    # WEBP: "RIFF" at offset 0, then "WEBP" at offset 8. Matching the offset-8
    # marker is the most specific single check (RIFF alone also matches WAV/AVI).
    "webp": [(8, b"WEBP")],
    "bmp":  [(0, b"BM")],
    # ZIP / DOCX / XLSX / PPTX all share the ZIP container signature
    "zip":  [(0, b"PK\x03\x04"), (0, b"PK\x05\x06"), (0, b"PK\x07\x08")],
    "docx": [(0, b"PK\x03\x04")],
    "xlsx": [(0, b"PK\x03\x04")],
    # Legacy OLE2 container — DOC, XLS, PPT
    "doc":  [(0, b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1")],
    "xls":  [(0, b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1")],
    # CSV has no magic — it's just text. We skip the magic check for csv and
    # rely on extension + content-type only.
}

# Extensions that legitimately have no recognizable magic bytes; magic check
# is skipped for these.
_NO_MAGIC_EXTENSIONS = {"csv", "txt"}


def detect_extension_mismatch(
    extension: str, content_head: bytes
) -> Optional[str]:
    """Verify the first bytes of an uploaded file match the declared extension.

    Returns None if OK, an error message string if mismatched.

    Why this matters: an attacker can rename evil.exe to evil.pdf and set the
    Content-Type to application/pdf. Without sniffing, the server would store
    and re-serve the file as a PDF. Downstream consumers (browsers, viewers,
    AV scanners) would then execute it.
    """
    ext = (extension or "").lower().lstrip(".")
    if not ext:
        return "missing extension"
    if ext in _NO_MAGIC_EXTENSIONS:
        return None
    sigs = _MAGIC_SIGNATURES.get(ext)
    if sigs is None:
        # Extension not in our known list. The settings.ALLOWED_EXTENSIONS gate
        # should have already rejected unknown extensions before we get here, so
        # this is a defense-in-depth fallback — refuse rather than skip.
        return f"no known magic-byte signature for .{ext}"
    for offset, magic in sigs:
        if content_head[offset : offset + len(magic)] == magic:
            return None
    return f"content does not match extension .{ext}"


_SLUG_RE = re.compile(r"[^a-z0-9]+")


def slugify(value: str, max_length: int = 80) -> str:
    """Return a lowercase, S3-key-safe slug (e.g. 'Bali & Ubud' -> 'bali-ubud').

    Used to build destination-namespaced folder prefixes for itinerary PDFs.
    Falls back to 'unknown' when the input has no usable characters.
    """
    if not value:
        return "unknown"
    normalized = unicodedata.normalize("NFKD", value).encode("ascii", "ignore").decode("ascii")
    slug = _SLUG_RE.sub("-", normalized.lower()).strip("-")
    return (slug[:max_length].strip("-") or "unknown")


def sanitize_filename(name: str, max_length: int = 200) -> str:
    """Return a filesystem- and S3-safe filename.

    Strips path components, normalizes unicode, replaces unsafe characters
    with `_`, and caps length. Prevents path traversal via `../` or absolute
    paths embedded in user-supplied filenames.
    """
    if not name:
        return "file"
    # Drop any directory parts (Windows or POSIX)
    base = os.path.basename(name.replace("\\", "/"))
    # Normalize unicode and drop combining characters that complicate equality
    base = unicodedata.normalize("NFKD", base).encode("ascii", "ignore").decode("ascii")
    base = _FILENAME_SAFE_RE.sub("_", base).strip(". _") or "file"
    if len(base) > max_length:
        stem, _, ext = base.rpartition(".")
        if stem and ext and len(ext) < 20:
            stem = stem[: max_length - len(ext) - 1]
            base = f"{stem}.{ext}"
        else:
            base = base[:max_length]
    return base

class LocalFileService:
    """Local file storage service for testing"""
    
    def __init__(self):
        self.upload_dir = Path("uploads")
        self.upload_dir.mkdir(exist_ok=True)
    
    async def upload_file(
        self,
        file_obj: BinaryIO,
        filename: str,
        content_type: str,
        tenant_id: Optional[ObjectId] = None,
        subfolder: str = "uploads",
    ) -> str:
        """Upload file to local storage and return file key.

        Tenant ID is included in the path so listing the local upload dir
        cannot accidentally cross-tenant. ``subfolder`` mirrors the S3 key
        prefix (e.g. ``itineraries/bali``).
        """

        safe_name = sanitize_filename(filename)
        timestamp = datetime.utcnow().strftime('%Y%m%d_%H%M%S')
        unique_filename = f"{timestamp}_{uuid.uuid4().hex[:8]}_{safe_name}"
        tenant_name = str(tenant_id) if tenant_id else "shared"
        dest_dir = self.upload_dir / tenant_name / subfolder
        dest_dir.mkdir(parents=True, exist_ok=True)
        file_path = dest_dir / unique_filename

        file_content = file_obj.read()
        with open(file_path, "wb") as f:
            f.write(file_content)

        return f"local_uploads/{tenant_name}/{subfolder}/{unique_filename}"
    
    async def download_file(self, file_key: str) -> bytes:
        """Download file from local storage.

        Raises FileNotFoundError both for a missing file and for a key that
        isn't a local key at all — callers treat either as "object gone".
        """

        if file_key.startswith("local_uploads/"):
            filename = file_key.replace("local_uploads/", "")
            file_path = self.upload_dir / filename

            with open(file_path, "rb") as f:
                return f.read()

        raise FileNotFoundError(f"Not a local storage key: {file_key}")
    
    async def delete_file(self, file_key: str) -> bool:
        """Delete file from local storage"""
        
        try:
            if file_key.startswith("local_uploads/"):
                filename = file_key.replace("local_uploads/", "")
                file_path = self.upload_dir / filename
                file_path.unlink()
                return True
            return False
        except Exception:
            return False
    
    async def get_presigned_url(
        self,
        file_key: str,
        expiration: int = 3600
    ) -> str:
        """Generate local file URL (for testing)"""
        
        if file_key.startswith("local_uploads/"):
            filename = file_key.replace("local_uploads/", "")
            return f"http://localhost:8000/files/local/{filename}"
        
        raise Exception("Invalid file key format")

class S3Service:
    """Service for AWS S3 operations with local storage fallback"""
    
    def __init__(self):
        # Local storage is always available: even a server configured for S3
        # must be able to serve/delete legacy files recorded with
        # storage_type == "local".
        self.local_service = LocalFileService()

        # Check if AWS credentials are properly configured
        if (settings.AWS_ACCESS_KEY_ID and
            settings.AWS_SECRET_ACCESS_KEY and
            settings.AWS_ACCESS_KEY_ID != "your_access_key" and
            settings.AWS_SECRET_ACCESS_KEY != "your_secret_key"):

            # Use AWS S3
            self.s3_client = boto3.client(
                's3',
                aws_access_key_id=settings.AWS_ACCESS_KEY_ID,
                aws_secret_access_key=settings.AWS_SECRET_ACCESS_KEY,
                region_name=settings.AWS_REGION
            )
            self.bucket_name = settings.S3_BUCKET_NAME
            self.use_aws = True
        else:
            # Fall back to local storage for uploads
            self.use_aws = False
    
    async def upload_file(
        self,
        file_obj: BinaryIO,
        filename: str,
        content_type: str,
        tenant_id: Optional[ObjectId] = None,
        subfolder: str = "uploads",
    ) -> str:
        """Upload file to S3 or local storage and return file key.

        S3 keys are tenant-namespaced (`{tenant_id}/{subfolder}/...`) so accidental
        unprefixed list/access of one tenant's bucket prefix cannot reveal
        another's data. ``subfolder`` lets callers namespace by feature — e.g.
        itinerary PDFs use ``itineraries/{destination}``.
        """

        safe_name = sanitize_filename(filename)
        timestamp = datetime.utcnow().strftime('%Y%m%d_%H%M%S')
        unique_suffix = uuid.uuid4().hex[:8]
        tenant_prefix = f"{tenant_id}/" if tenant_id else "shared/"

        if self.use_aws:
            s3_key = f"{tenant_prefix}{subfolder}/{timestamp}_{unique_suffix}_{safe_name}"

            self.s3_client.upload_fileobj(
                file_obj,
                self.bucket_name,
                s3_key,
                ExtraArgs={'ContentType': content_type}
            )

            return s3_key
        else:
            return await self.local_service.upload_file(
                file_obj, filename, content_type, tenant_id=tenant_id, subfolder=subfolder
            )
    
    async def download_s3(self, file_key: str) -> bytes:
        """Download an object stored in S3. Requires S3 to be configured.

        Raises StorageBackendUnavailable when the server has no S3 credentials,
        FileNotFoundError when the object no longer exists in the bucket.
        """
        if not self.use_aws:
            raise StorageBackendUnavailable(
                "This file is stored in S3, but file storage (S3) is not "
                "configured on this server. Ask your administrator to set the "
                "AWS credentials in the backend environment."
            )
        try:
            response = self.s3_client.get_object(
                Bucket=self.bucket_name,
                Key=file_key
            )
        except ClientError as e:
            code = e.response.get("Error", {}).get("Code", "")
            if code in ("NoSuchKey", "404"):
                raise FileNotFoundError(f"S3 object missing: {file_key}") from e
            raise
        return response['Body'].read()

    async def download_local(self, file_key: str) -> bytes:
        """Download an object stored on this server's local disk."""
        return await self.local_service.download_file(file_key)

    async def delete_file(self, file_key: str, storage_type: str = None) -> bool:
        """Delete a stored object from the backend it was stored with.

        ``storage_type`` is the File record's value ("s3" | "local"); when
        omitted, falls back to the server's current backend (legacy behavior).
        """
        if storage_type is None:
            storage_type = "s3" if self.use_aws else "local"

        if storage_type == "s3":
            if not self.use_aws:
                _logger.warning(
                    "Cannot delete S3 object %s — S3 is not configured on this server",
                    file_key,
                )
                return False
            try:
                self.s3_client.delete_object(
                    Bucket=self.bucket_name,
                    Key=file_key
                )
                return True
            except Exception:
                return False
        else:
            return await self.local_service.delete_file(file_key)
    
    async def get_presigned_url(
        self,
        file_key: str,
        expiration: int = 3600
    ) -> str:
        """Generate presigned URL for temporary access"""
        
        if self.use_aws:
            return self.s3_client.generate_presigned_url(
                'get_object',
                Params={'Bucket': self.bucket_name, 'Key': file_key},
                ExpiresIn=expiration
            )
        else:
            return await self.local_service.get_presigned_url(file_key, expiration)


class FileService:
    """Service for File management"""
    
    def __init__(self):
        self.s3_service = S3Service()
    
    async def upload_file(
        self,
        file_obj: BinaryIO,
        filename: str,
        content_type: str,
        file_size: int,
        user_id: ObjectId,
        tenant_id: ObjectId,
        fileable_type: Optional[str] = None,
        fileable_id: Optional[str] = None,
        category: Optional[str] = None,
        subfolder: str = "uploads",
    ) -> File:
        """Upload file and create file record. Filename is sanitized; S3 key is tenant-namespaced."""

        # In production a silent fall-back to container-local disk means the
        # file is quietly lost on the next redeploy. Fail loudly instead so a
        # missing-credentials misconfiguration is caught immediately.
        if not self.s3_service.use_aws and settings.ENVIRONMENT == "production":
            _logger.critical(
                "Rejecting upload of %s: AWS S3 credentials are not configured "
                "on this production server — files would be written to the "
                "container's ephemeral disk and lost on redeploy.",
                filename,
            )
            raise StorageBackendUnavailable(
                "File storage (S3) is not configured on the server, so the "
                "upload cannot be stored safely. Ask your administrator to set "
                "the AWS credentials in the backend environment."
            )

        safe_name = sanitize_filename(filename)
        s3_key = await self.s3_service.upload_file(
            file_obj,
            safe_name,
            content_type,
            tenant_id=tenant_id,
            subfolder=subfolder,
        )

        # Record the storage backend that was ACTUALLY used. Hardcoding "s3"
        # mislabels files written by the local fallback (when AWS creds are
        # absent), which then 404 on download because the key isn't in S3.
        used_s3 = self.s3_service.use_aws
        file_record = File(
            filename=safe_name,
            original_filename=filename,
            file_path=s3_key,
            file_size=file_size,
            mime_type=content_type,
            storage_type="s3" if used_s3 else "local",
            s3_bucket=settings.S3_BUCKET_NAME if used_s3 else None,
            s3_key=s3_key,
            fileable_type=fileable_type,
            fileable_id=ObjectId(fileable_id) if fileable_id else None,
            category=category,
            tenant_id=tenant_id,
            owner_id=user_id,
            created_by=user_id
        )

        await file_record.insert()
        return file_record

    async def get_file(
        self,
        file_id: str,
        tenant_id: ObjectId
    ) -> Optional[File]:
        """Get file by ID, scoped to tenant."""
        try:
            oid = ObjectId(file_id)
        except Exception:
            return None
        return await File.find_one(
            {"_id": oid, "tenant_id": tenant_id, "deleted_at": None}
        )
    
    async def download_file(
        self,
        file_id: str,
        tenant_id: ObjectId
    ) -> Optional[tuple[bytes, str, str]]:
        """Download file content.

        Routes by the backend the file was STORED with (the record's
        ``storage_type``), never by the server's current backend: a file
        uploaded to S3 must not be looked up on local disk (and vice versa)
        just because this server's credentials changed.

        Returns None when the record or the stored object is gone (→ 404).
        Raises StorageBackendUnavailable when the record says S3 but this
        server has no S3 credentials (→ 503, a deploy misconfiguration).
        """
        file_record = await self.get_file(file_id, tenant_id)

        if not file_record:
            return None

        try:
            if file_record.storage_type == "s3":
                content = await self.s3_service.download_s3(file_record.s3_key)
            else:
                content = await self.s3_service.download_local(file_record.s3_key)
        except FileNotFoundError:
            # Record exists but the stored bytes are gone — e.g. it was written
            # to a container's local disk that has since been redeployed.
            _logger.warning(
                "Stored object missing for file %s (storage=%s, key=%s)",
                file_id, file_record.storage_type, file_record.s3_key,
            )
            return None

        # Increment download count
        await file_record.increment_download_count()

        return content, file_record.original_filename, file_record.mime_type
    
    async def delete_file(
        self,
        file_id: str,
        tenant_id: ObjectId,
        user_id: ObjectId
    ) -> bool:
        """Delete file"""
        file_record = await self.get_file(file_id, tenant_id)
        
        if not file_record:
            return False
        
        # Only owner can delete
        if file_record.owner_id != user_id:
            return False

        # Delete the stored object from the backend it was stored with; the
        # record is soft-deleted regardless so a storage hiccup can't leave a
        # "live" record pointing at a half-deleted file.
        await self.s3_service.delete_file(
            file_record.s3_key, storage_type=file_record.storage_type
        )

        # Soft delete record
        await file_record.soft_delete()
        return True
    
    async def get_user_files(
        self,
        user_id: ObjectId,
        tenant_id: ObjectId,
        fileable_type: Optional[str] = None,
        fileable_id: Optional[str] = None,
        page: int = 1,
        per_page: int = 10
    ) -> tuple[List[File], int]:
        """Get all files for a user with pagination"""
        
        # Build query
        query = {
            "owner_id": user_id,
            "tenant_id": tenant_id,
            "deleted_at": None
        }
        
        if fileable_type:
            query["fileable_type"] = fileable_type
        if fileable_id:
            query["fileable_id"] = ObjectId(fileable_id)
        
        # Get total count
        total = await File.find(query).count()
        
        # Get files with pagination
        skip = (page - 1) * per_page
        files = await File.find(query).sort("-created_at").skip(skip).limit(per_page).to_list()
        
        return files, total
    
    async def get_files_by_entity(
        self,
        fileable_type: str,
        fileable_id: str,
        tenant_id: ObjectId
    ) -> List[File]:
        """Get all files for a specific entity"""
        files = await File.find(
            {"fileable_type": fileable_type, "fileable_id": ObjectId(fileable_id), "tenant_id": tenant_id, "deleted_at": None}
        ).sort("-created_at").to_list()
        
        return files
    
    async def get_presigned_url(
        self,
        file_id: str,
        tenant_id: ObjectId,
        expiration: int = 3600
    ) -> Optional[str]:
        """Get presigned URL for file"""
        file_record = await self.get_file(file_id, tenant_id)

        # Presigning only makes sense for S3-stored files on a server that has
        # S3 configured — otherwise S3Service would hand back a bogus
        # localhost URL for an S3 key.
        if (
            not file_record
            or file_record.storage_type != "s3"
            or not self.s3_service.use_aws
        ):
            return None
        
        url = await self.s3_service.get_presigned_url(
            file_record.s3_key,
            expiration
        )
        
        return url
