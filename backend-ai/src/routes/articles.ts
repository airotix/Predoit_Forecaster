import { Router, Request, Response } from "express";
import { ArticleData, Season, FilterOptions } from "../types";
import { mockArticles } from "../data/mockData";

const VALID_SEASONS: Season[] = ["SS2024", "FW2024", "SS2025", "FW2025"];

const router = Router();

function filterArticles(
  articles: ArticleData[],
  season: Season,
  filters: {
    supplier?: string;
    family?: string;
    theme?: string;
    model?: string;
    customer?: string;
    searchQuery?: string;
  }
): ArticleData[] {
  let data = articles.filter((a) => a.season === season);

  if (filters.supplier && filters.supplier !== "All") {
    data = data.filter((a) => a.supplier === filters.supplier);
  }
  if (filters.family && filters.family !== "All") {
    data = data.filter((a) => a.family === filters.family);
  }
  if (filters.theme && filters.theme !== "All") {
    data = data.filter((a) => a.theme === filters.theme);
  }
  if (filters.model && filters.model !== "All") {
    data = data.filter((a) => a.model === filters.model);
  }
  if (filters.customer && filters.customer !== "All") {
    data = data.filter((a) => a.customer === filters.customer);
  }
  if (filters.searchQuery) {
    const q = filters.searchQuery.toLowerCase();
    data = data.filter(
      (a) =>
        a.id.toLowerCase().includes(q) ||
        a.supplier.toLowerCase().includes(q) ||
        a.customer.toLowerCase().includes(q)
    );
  }

  return data;
}

router.get("/articles", (req: Request, res: Response) => {
  const season = req.query.season as Season | undefined;
  if (!season || !VALID_SEASONS.includes(season)) {
    res.status(400).json({
      error: "Invalid or missing season",
      validSeasons: VALID_SEASONS,
    });
    return;
  }

  const filters = {
    supplier: req.query.supplier as string | undefined,
    family: req.query.family as string | undefined,
    theme: req.query.theme as string | undefined,
    model: req.query.model as string | undefined,
    customer: req.query.customer as string | undefined,
    searchQuery: req.query.searchQuery as string | undefined,
  };

  const articles = filterArticles(mockArticles, season, filters);
  res.json(articles);
});

router.get("/filter-options", (req: Request, res: Response) => {
  const season = req.query.season as Season | undefined;
  if (!season || !VALID_SEASONS.includes(season)) {
    res.status(400).json({
      error: "Invalid or missing season",
      validSeasons: VALID_SEASONS,
    });
    return;
  }

  const seasonData = mockArticles.filter((a) => a.season === season);

  const getUnique = (key: keyof ArticleData) =>
    Array.from(new Set(seasonData.map((a) => a[key] as string))).sort();

  const options: FilterOptions = {
    suppliers: ["All", ...getUnique("supplier")],
    families: ["All", ...getUnique("family")],
    themes: ["All", ...getUnique("theme")],
    models: ["All", ...getUnique("model")],
    customers: ["All", ...getUnique("customer")],
  };

  res.json(options);
});

export default router;
