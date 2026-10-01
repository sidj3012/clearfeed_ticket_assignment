import type { Metadata } from "next";
import "./styles.css";

// Set the browser tab title and a short description for the app.
export const metadata: Metadata = {
  title: "Ticket Assignment | Team setup",
  description: "Manage agent timezones, capacity, and weekly availability.",
};

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  // Provide the shared document shell around the active workspace page.
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}
