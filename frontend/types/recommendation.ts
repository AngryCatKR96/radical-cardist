export type RecommendationCard = {
  id: string;
  name: string;
  brand: string;
  annual_fee: string;
  required_spend: string;
  benefits: string[];
  monthly_savings: number;
  annual_savings: number;
  homepage_url?: string | null;
};

export type RecommendationAnalysis = {
  annual_savings: number;
  monthly_savings: number;
  net_benefit: number;
  annual_fee: number;
  warnings: string[];
  category_breakdown: Record<string, number>;
  conditions_met: boolean;
};

export type RecommendResponse = {
  card: RecommendationCard;
  explanation: string;
  analysis: RecommendationAnalysis;
};

