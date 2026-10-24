import { CampaignDetailView } from "@/components/CampaignDetailView";

export default async function CampaignPage({
  params,
}: {
  params: Promise<{ campaignId: string }>;
}) {
  const { campaignId } = await params;
  return <CampaignDetailView campaignId={campaignId} />;
}
