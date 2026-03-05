import { redirect } from "next/navigation";

// This file is superseded by (dashboard)/page.tsx at the same "/" route.
// Next.js route groups take precedence; this is a safety fallback.
export default function RootPage() {
  redirect("/login");
}
