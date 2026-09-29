import type { Metadata } from "next";
import "./styles.css";

export const metadata: Metadata = {
  title: "Ticket Assignment | Team setup",
  description: "Manage agent timezones, capacity, and weekly availability.",
};

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}
