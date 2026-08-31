import type { Metadata } from "next";
import { ProfilePage } from "../../components/profile-page";

export const metadata: Metadata = {
  title: "My Trove | TamilTrove",
  description:
    "Manage your watchlist, preferences, privacy, and recommendation data.",
};
export default function MyTrovePage() {
  return <ProfilePage />;
}
