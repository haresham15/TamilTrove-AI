import type { Metadata } from "next";
import { RecommendationsPage } from "../../components/recommendations-page";

export const metadata: Metadata = {
  title: "For You | TamilTrove",
  description:
    "Personalized Tamil film recommendations shaped by your explicit preferences.",
};

export default function ForYouPage() {
  return <RecommendationsPage />;
}
