"""
Itinerary API endpoints — Travel-industry module (simple PDF-upload model).

All routes are guarded by ``require_module("itineraries")`` so only tenants
with the itineraries module enabled can access them.
"""
import os
from io import BytesIO
from typing import List, Optional

from bson import ObjectId
from fastapi import APIRouter, Depends, HTTPException, Query, UploadFile, File as FastAPIFile, Form
from fastapi.responses import StreamingResponse

from app.core.config import settings
from app.core.picklist_query import build_picklist_query
from app.models.consolidated_picklists import DestinationPicklist
from app.models.user import User
from app.schemas.itinerary import (
    ItineraryUpdate, ItineraryResponse, ItineraryListResponse,
)
from app.services.file_service import FileService, detect_extension_mismatch, slugify
from app.services.itinerary_service import ItineraryService
from app.services.visibility_scope import get_visible_owner_ids, is_record_visible
from app.api.deps import check_permission
from app.middleware.industry_guard import require_module

router = APIRouter(dependencies=[Depends(require_module("itineraries"))])


async def _resolve_destination_names(
    destination_ids: List[str], tenant_id: ObjectId
) -> tuple[List[ObjectId], List[str]]:
    """Resolve picklist destination ids -> (ObjectId list, name list), tenant-scoped.

    Names are resolved server-side from the destination picklist (platform
    defaults + this tenant's overrides) — never trusted from the client. The
    returned lists preserve the caller's selection order so index 0 stays the
    primary destination.
    """
    oids: List[ObjectId] = []
    for d in destination_ids:
        d = (d or "").strip()
        if not d:
            continue
        try:
            oids.append(ObjectId(d))
        except Exception:
            raise HTTPException(status_code=400, detail=f"Invalid destination id: {d}")

    if not oids:
        raise HTTPException(status_code=400, detail="At least one destination is required")

    query = build_picklist_query(tenant_id, picklist_type="destination", active_only=False)
    query["_id"] = {"$in": oids}
    items = await DestinationPicklist.find(query).to_list()
    name_by_id = {item.id: item.name for item in items}

    resolved_ids: List[ObjectId] = []
    resolved_names: List[str] = []
    for oid in oids:
        name = name_by_id.get(oid)
        if name:
            resolved_ids.append(oid)
            resolved_names.append(name)
    if not resolved_ids:
        raise HTTPException(status_code=400, detail="No valid destinations found")
    return resolved_ids, resolved_names


@router.post("/upload", response_model=ItineraryResponse, status_code=201)
async def upload_itinerary(
    name: str = Form(...),
    destination_ids: str = Form(...),  # comma-separated picklist destination ids
    file: UploadFile = FastAPIFile(...),
    opportunity_id: Optional[str] = Form(None),
    current_user: User = Depends(check_permission("create_itinerary")),
):
    """Create an itinerary from an uploaded PDF, organized in S3 by destination.

    The PDF is stored via the polymorphic File model under
    ``{tenant}/itineraries/{primary-destination}/…`` and linked back via
    ``Itinerary.pdf_file_id``. Optionally auto-attaches to an opportunity.
    """
    service = ItineraryService()

    name = (name or "").strip()
    if not name:
        raise HTTPException(status_code=400, detail="Name is required")

    # --- Validate the PDF (mirrors app/api/v1/files.py) ---
    if not file.filename:
        raise HTTPException(status_code=400, detail="Filename is required")
    _, ext = os.path.splitext(file.filename)
    ext = ext.lower().lstrip(".")
    if ext != "pdf":
        raise HTTPException(status_code=400, detail="Only PDF files are allowed")

    content = await file.read()
    if len(content) == 0:
        raise HTTPException(status_code=400, detail="File is empty")
    if len(content) > settings.MAX_FILE_SIZE:
        raise HTTPException(
            status_code=413,
            detail=f"File too large. Max size: {settings.MAX_FILE_SIZE // (1024 * 1024)}MB",
        )
    mismatch = detect_extension_mismatch(ext, content[:32])
    if mismatch:
        raise HTTPException(
            status_code=400,
            detail=f"File content does not match declared type: {mismatch}",
        )

    # --- Resolve destinations (tenant-scoped) ---
    dest_ids = [d for d in destination_ids.split(",")]
    resolved_ids, resolved_names = await _resolve_destination_names(dest_ids, current_user.tenant_id)

    # --- Create the itinerary record, then upload + link the PDF ---
    itinerary = await service.create_uploaded_itinerary(
        name=name,
        destination_ids=resolved_ids,
        destination_names=resolved_names,
        user_id=current_user.id,
        tenant_id=current_user.tenant_id,
    )

    primary_slug = slugify(resolved_names[0])
    file_service = FileService()
    try:
        file_record = await file_service.upload_file(
            file_obj=BytesIO(content),
            filename=file.filename,
            content_type=file.content_type or "application/pdf",
            file_size=len(content),
            user_id=current_user.id,
            tenant_id=current_user.tenant_id,
            fileable_type="Itinerary",
            fileable_id=str(itinerary.id),
            category="itinerary_pdf",
            subfolder=f"itineraries/{primary_slug}",
        )
    except Exception:
        # Roll back the bare itinerary so we don't leave a PDF-less orphan
        await itinerary.soft_delete()
        raise HTTPException(status_code=500, detail="File upload failed")

    itinerary.pdf_file_id = file_record.id
    await itinerary.save()

    # --- Optional auto-attach to an opportunity ---
    if opportunity_id:
        try:
            await service.link_to_opportunity(
                str(itinerary.id), opportunity_id, current_user.tenant_id
            )
        except ValueError as e:
            # Roll back so a failed attach doesn't leave an orphaned itinerary/PDF.
            await file_service.delete_file(str(file_record.id), current_user.tenant_id, current_user.id)
            await itinerary.soft_delete()
            raise HTTPException(status_code=400, detail=str(e))

    return ItineraryResponse.from_orm(itinerary)


@router.get("/", response_model=ItineraryListResponse)
async def get_itineraries(
    search: Optional[str] = None,
    is_template: Optional[bool] = None,
    current_user: User = Depends(check_permission("view_itinerary")),
):
    """List itineraries (tenant + visibility scoped), searchable by name/destination."""
    service = ItineraryService()

    visible_owner_ids = await get_visible_owner_ids(current_user)
    itineraries = await service.get_itineraries_by_tenant(
        current_user.tenant_id,
        search=search,
        visible_owner_ids=visible_owner_ids,
        is_template=is_template,
    )

    return ItineraryListResponse(
        itineraries=[ItineraryResponse.from_orm(i) for i in itineraries],
        total=len(itineraries),
    )


@router.get("/{itinerary_id}", response_model=ItineraryResponse)
async def get_itinerary(
    itinerary_id: str,
    current_user: User = Depends(check_permission("view_itinerary")),
):
    """Get a single itinerary by ID."""
    service = ItineraryService()

    itinerary = await service.get_itinerary(itinerary_id, current_user.tenant_id)
    if not itinerary:
        raise HTTPException(status_code=404, detail="Itinerary not found")

    visible_owner_ids = await get_visible_owner_ids(current_user)
    if not is_record_visible(itinerary.owner_id, visible_owner_ids):
        raise HTTPException(status_code=404, detail="Itinerary not found")

    return ItineraryResponse.from_orm(itinerary)


@router.get("/{itinerary_id}/pdf")
async def get_itinerary_pdf(
    itinerary_id: str,
    current_user: User = Depends(check_permission("view_itinerary")),
):
    """Stream the itinerary's PDF inline.

    Streams through the backend (rather than handing out a presigned URL) so it
    works with BOTH S3 and local-disk storage, and so access is gated by
    ``view_itinerary`` — the same permission that lets the user see the record.
    """
    service = ItineraryService()

    itinerary = await service.get_itinerary(itinerary_id, current_user.tenant_id)
    if not itinerary or not itinerary.pdf_file_id:
        raise HTTPException(status_code=404, detail="Itinerary PDF not found")

    file_service = FileService()
    result = await file_service.download_file(str(itinerary.pdf_file_id), current_user.tenant_id)
    if not result:
        raise HTTPException(status_code=404, detail="Itinerary PDF not found")

    content, filename, mime_type = result
    return StreamingResponse(
        BytesIO(content),
        media_type=mime_type or "application/pdf",
        headers={"Content-Disposition": f'inline; filename="{filename}"'},
    )


@router.put("/{itinerary_id}", response_model=ItineraryResponse)
async def update_itinerary(
    itinerary_id: str,
    itinerary_data: ItineraryUpdate,
    current_user: User = Depends(check_permission("edit_itinerary")),
):
    """Update itinerary metadata (rename / notes / active)."""
    service = ItineraryService()

    itinerary = await service.update_itinerary(
        itinerary_id,
        itinerary_data,
        current_user.id,
        current_user.tenant_id,
    )

    if not itinerary:
        raise HTTPException(status_code=404, detail="Itinerary not found")

    return ItineraryResponse.from_orm(itinerary)


@router.delete("/{itinerary_id}")
async def delete_itinerary(
    itinerary_id: str,
    current_user: User = Depends(check_permission("delete_itinerary")),
):
    """Delete an itinerary (soft delete)."""
    service = ItineraryService()

    success = await service.delete_itinerary(itinerary_id, current_user.tenant_id)

    if not success:
        raise HTTPException(status_code=404, detail="Itinerary not found")

    return {
        "error": False,
        "message": "Itinerary deleted successfully",
    }


@router.post("/opportunity/{opportunity_id}/link")
async def link_itinerary_to_opportunity(
    opportunity_id: str,
    itinerary_id: str = Query(...),
    notes: Optional[str] = None,
    current_user: User = Depends(check_permission("edit_opportunity")),
):
    """Link an existing itinerary to an opportunity."""
    service = ItineraryService()

    try:
        await service.link_to_opportunity(
            itinerary_id,
            opportunity_id,
            current_user.tenant_id,
            notes=notes,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    return {
        "error": False,
        "message": "Itinerary linked to opportunity successfully",
    }


@router.delete("/opportunity/{opportunity_id}/unlink")
async def unlink_itinerary_from_opportunity(
    opportunity_id: str,
    itinerary_id: str = Query(...),
    current_user: User = Depends(check_permission("edit_opportunity")),
):
    """Unlink an itinerary from an opportunity."""
    service = ItineraryService()

    success = await service.unlink_from_opportunity(
        itinerary_id, opportunity_id, current_user.tenant_id
    )

    if not success:
        raise HTTPException(status_code=404, detail="Link not found")

    return {
        "error": False,
        "message": "Itinerary unlinked from opportunity successfully",
    }


@router.get("/opportunity/{opportunity_id}")
async def get_opportunity_itineraries(
    opportunity_id: str,
    current_user: User = Depends(check_permission("view_opportunity")),
):
    """Get all itineraries attached to an opportunity."""
    service = ItineraryService()

    itineraries = await service.get_itineraries_for_opportunity(
        opportunity_id,
        current_user.tenant_id,
    )

    return {
        "itineraries": [
            {
                "itinerary": ItineraryResponse.from_orm(i["itinerary"]),
                "notes": i["notes"],
            }
            for i in itineraries
        ],
        "total": len(itineraries),
    }
