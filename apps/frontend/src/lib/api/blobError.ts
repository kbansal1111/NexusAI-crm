import { AxiosError } from "axios";

/**
 * Extract the backend's `detail` message from a failed blob request.
 *
 * Requests made with `responseType: "blob"` receive their JSON error body as
 * a Blob, so `error.response.data.detail` is not directly readable. Decoding
 * it lets the UI show the real reason (e.g. "File storage (S3) is not
 * configured on the server") instead of a generic "Download failed".
 */
export async function blobErrorDetail(error: unknown): Promise<string | null> {
    const data = (error as AxiosError | undefined)?.response?.data;
    if (!(data instanceof Blob)) return null;
    try {
        const parsed = JSON.parse(await data.text());
        return typeof parsed?.detail === "string" ? parsed.detail : null;
    } catch {
        return null;
    }
}
