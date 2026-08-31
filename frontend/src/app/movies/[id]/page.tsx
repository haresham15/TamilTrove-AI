import type { Metadata } from "next";
import { MovieDetail } from "../../../components/movie-detail";

export async function generateMetadata({
  params,
}: PageProps<"/movies/[id]">): Promise<Metadata> {
  const { id } = await params;
  return {
    title: `Movie details | TamilTrove`,
    description: `Canonical Tamil film metadata, match evidence, and similar films for ${id}.`,
  };
}

export default async function MoviePage({ params }: PageProps<"/movies/[id]">) {
  const { id } = await params;
  return <MovieDetail id={id} />;
}
