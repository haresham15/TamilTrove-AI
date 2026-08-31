import type { Metadata } from "next";
import { AuthPage } from "../../components/auth-page";

export const metadata: Metadata = {
  title: "Sign in | TamilTrove",
  description: "Sign in to save and personalize your Tamil film discoveries.",
};

export default function SignInPage() {
  return <AuthPage />;
}
