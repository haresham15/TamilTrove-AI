import type { Metadata } from "next";
import { CollectionsPage } from "../../components/collections-page";

export const metadata: Metadata = {
  title: "Collections | TamilTrove",
  description: "Build private or shareable collections of Tamil films.",
};
export default function CollectionsRoute() {
  return <CollectionsPage />;
}
