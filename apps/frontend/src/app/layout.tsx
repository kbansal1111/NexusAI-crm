import type { Metadata, Viewport } from "next";
import { Inter, Space_Grotesk, JetBrains_Mono } from "next/font/google";
import "./globals.css";
import "./error-feedback.css";
import { Providers } from "@/lib/providers";
import { PageErrorBoundary } from "@/components/ui/error-boundary";
import { getServerSession } from "next-auth";
import { authOptions } from "@/lib/auth";

const inter = Inter({ subsets: ["latin"], variable: "--font-inter" });
const spaceGrotesk = Space_Grotesk({
  subsets: ["latin"],
  variable: "--font-space-grotesk",
  weight: ["400", "500", "600", "700"],
});
const jetbrainsMono = JetBrains_Mono({
  subsets: ["latin"],
  variable: "--font-jetbrains-mono",
  weight: ["400", "500", "600"],
});

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
    <html
      lang="en"
      className={`${inter.variable} ${spaceGrotesk.variable} ${jetbrainsMono.variable}`}
      suppressHydrationWarning
    >
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
              __html: `(function(){var AS=["fdprocessedid","bis_skin_checked","bis_register","__processed"];var sa=Element.prototype.setAttribute;Element.prototype.setAttribute=function(n,v){if(AS.indexOf(n)!==-1)return;return sa.call(this,n,v)};var s=function(){AS.forEach(function(A){document.querySelectorAll("["+A+"]").forEach(function(e){e.removeAttribute(A)})})};s();var o=new MutationObserver(function(m){m.forEach(function(x){if(x.attributeName&&AS.indexOf(x.attributeName)!==-1)x.target.removeAttribute(x.attributeName)})});o.observe(document.documentElement,{attributes:true,subtree:true,attributeFilter:AS})})();`,
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
