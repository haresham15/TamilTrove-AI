import { CollectionDetail } from "../../../components/collection-detail";

export default async function CollectionPage({
  params,
}: PageProps<"/collections/[id]">) {
  const { id } = await params;
  return <CollectionDetail id={id} />;
}
