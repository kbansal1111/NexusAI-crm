import type { Metadata, Viewport } from "next";
import { Inter } from "next/font/google";
import "./globals.css";
import "./error-feedback.css";
import { Providers } from "@/lib/providers";
import { PageErrorBoundary } from "@/components/ui/error-boundary";
import { getServerSession } from "next-auth";
import { authOptions } from "@/lib/auth";

const inter = Inter({ subsets: ["latin"], variable: "--font-inter" });

export const metadata: Metadata = {
  title: "Travel CRM",
  description: "Next Gen Travel CRM",
};

// Explicit mobile viewport (App Router would default to this, but a
// mobile-facing CRM should not rely on the framework default).
export const viewport: Viewport = {
  width: "device-width",
  initialScale: 1,
};

import { Toaster } from "@/components/ui/sonner";

export default async function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  const session = await getServerSession(authOptions);

  return (
    // suppressHydrationWarning on <html> and <body> is required to silence
    // false-positive hydration mismatches caused by browser extensions
    // (Grammarly, LastPass, ColorZilla, etc.) that inject attributes like
    // `data-new-gr-c-s-check-loaded` into the document before React hydrates.
    // This is a known and accepted pattern — see
    // https://nextjs.org/docs/messages/react-hydration-error
    <html lang="en" className={inter.variable} suppressHydrationWarning>
      <body className="font-sans antialiased" suppressHydrationWarning>
        {process.env.NODE_ENV === "development" && (
          // Dev-only: download-manager/form-filler extensions (FDM/IDM) stamp
          // `fdprocessedid` onto buttons/inputs before React hydrates, which
          // triggers a false-positive hydration-mismatch warning on every page.
          // Strip the attribute at parse time and keep stripping until the page
          // has settled. Production builds don't log hydration warnings, so
          // this shim is not shipped there.
          <script
            dangerouslySetInnerHTML={{
              __html: `(function(){var A="fdprocessedid";var s=function(){document.querySelectorAll("["+A+"]").forEach(function(e){e.removeAttribute(A)})};s();var o=new MutationObserver(function(m){m.forEach(function(x){if(x.attributeName===A)x.target.removeAttribute(A)})});o.observe(document.documentElement,{attributes:true,subtree:true,attributeFilter:[A]});window.addEventListener("load",function(){setTimeout(function(){o.disconnect()},5000)})})();`,
            }}
          />
        )}
        <PageErrorBoundary>
          <Providers session={session}>
            {children}
            <Toaster />
          </Providers>
        </PageErrorBoundary>
      </body>
    </html>
  );
}
