import type { Metadata } from "next";
import { OnboardingPage } from "../../components/onboarding-page";

export const metadata: Metadata = {
  title: "Tune your taste | TamilTrove",
  description:
    "Set transparent preferences for your Tamil film recommendations.",
};
export default function TasteOnboardingPage() {
  return <OnboardingPage />;
}
