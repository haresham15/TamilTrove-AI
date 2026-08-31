import type { Metadata } from "next";
import { DataQualityPage } from "../../../components/data-quality-page";

export const metadata: Metadata = {
  title: "Data quality | TamilTrove Admin",
  robots: { index: false, follow: false },
};
export default function AdminDataQualityPage() {
  return <DataQualityPage />;
}
