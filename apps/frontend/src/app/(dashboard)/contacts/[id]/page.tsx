import { redirect } from "next/navigation";
import { getServerSession } from "next-auth";
import { authOptions } from "@/lib/auth";
import { ContactDetails } from "@/features/contacts/components/ContactDetails";
import { getApiBaseUrlNoSlash } from "@/lib/env";
import { fetchWithRetry } from "@/lib/server-fetch";
import { describeHttpError, isNotFound } from "@/lib/http-error";

export const dynamic = "force-dynamic";

interface ContactPageProps {
    params: Promise<{
        id: string;
    }>;
}

async function getContactDetail(id: string, token: string) {
    const res = await fetchWithRetry(
        `${getApiBaseUrlNoSlash()}/contacts/${id}?include_related=true`,
        {
            headers: {
                Authorization: `Bearer ${token}`,
            },
            cache: "no-store",
        }
    );

    if (!res.ok) {
        // Carry the status on the error: the caller distinguishes "deleted"
        // (404) from a real failure, and a bare Error would lose that.
        const err = new Error(`Failed to fetch contact (${res.status})`) as Error & { status?: number };
        err.status = res.status;
        throw err;
    }

    return res.json();
}

export default async function ContactPage(props: ContactPageProps) {
    const session = await getServerSession(authOptions);

    if (!session || !session.accessToken) {
        redirect("/login");
    }

    const params = await props.params;
    const { id } = params;

    try {
        const contact = await getContactDetail(id, session.accessToken);

        if (!contact) {
            return (
                <div className="flex flex-col items-center justify-center min-h-[400px] space-y-4">
                    <h2 className="text-2xl font-semibold">Contact not found</h2>
                    <p className="text-muted-foreground">The contact you are looking for does not exist or has been deleted.</p>
                </div>
            );
        }

        return (
            <div className="container mx-auto py-6">
                <ContactDetails contact={contact} />
            </div>
        );
    } catch (error) {
        // A deleted contact 404s, which throws — so it lands here rather than
        // in the `!contact` branch above. Report it as missing, not as a fault.
        if (isNotFound(error)) {
            return (
                <div className="flex flex-col items-center justify-center min-h-[400px] space-y-4">
                    <h2 className="text-2xl font-semibold">Contact not found</h2>
                    <p className="text-muted-foreground">The contact you are looking for does not exist or has been deleted.</p>
                </div>
            );
        }

        // Summary only — the raw error carries the bearer token.
        console.error("Error fetching contact data:", describeHttpError(error));
        return (
            <div className="flex flex-col items-center justify-center min-h-[400px] space-y-4 text-red-600">
                <h2 className="text-2xl font-semibold">Error Loading Contact</h2>
                <p>There was a problem loading the contact data. Please try again later.</p>
            </div>
        );
    }
}
