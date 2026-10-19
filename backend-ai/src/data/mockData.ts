import { ArticleData, Season, ForecastMatrixValue } from "../types";

const SEASONS: Season[] = ["SS2024", "FW2024", "SS2025", "FW2025"];
const SUPPLIERS = ["ABC Textiles", "Global Weaves", "Prime Fabric", "Silk Route"];
const CUSTOMERS = ["Zara Spain", "H&M UK", "Uniqlo Japan", "Mango France", "Nike US"];
const FAMILIES = ["Outerwear", "Tops", "Bottoms", "Accessories", "Footwear"];
const THEMES = ["Urban", "Classic", "Sport", "Business", "Casual"];
const MODELS = ["Jacket", "T-Shirt", "Pants", "Sneakers", "Sweater"];
const COLORS = ["Red", "Blue", "Black", "White", "Green", "Navy", "Grey"];
const SIZES = ["XS", "S", "M", "L", "XL", "XXL"];

const seededRandom = (seed: number) => {
  const x = Math.sin(seed++) * 10000;
  return x - Math.floor(x);
};

const getRandomElement = <T>(arr: T[], seed: number): T => {
  return arr[Math.floor(seededRandom(seed) * arr.length)];
};

const getRandomInt = (min: number, max: number, seed: number) => {
  return Math.floor(seededRandom(seed) * (max - min + 1)) + min;
};

const generateDemandTrend = (seed: number) => {
  const trend: { date: string; value: number }[] = [];
  const baseValue = getRandomInt(10, 100, seed);
  for (let i = 0; i < 12; i++) {
    const variance = Math.sin((i * Math.PI) / 6) * getRandomInt(5, 20, seed + i);
    trend.push({
      date: `Month ${i + 1}`,
      value: Math.max(
        0,
        Math.floor(
          baseValue + variance + (seededRandom(seed + i * 10) * 10 - 5)
        )
      ),
    });
  }
  return trend;
};

const generateMatrix = (
  colors: string[],
  sizes: string[],
  seed: number
): Record<string, Record<string, ForecastMatrixValue>> => {
  const matrix: Record<string, Record<string, ForecastMatrixValue>> = {};

  colors.forEach((color, cIdx) => {
    matrix[color] = {};
    sizes.forEach((size, sIdx) => {
      const cellSeed = seed + cIdx * 10 + sIdx;
      const stock = getRandomInt(0, 100, cellSeed);
      const orders = getRandomInt(0, 80, cellSeed + 1);

      const riskRoll = seededRandom(cellSeed + 2);
      let forecast: number;
      if (riskRoll < 0.1) {
        forecast = stock + getRandomInt(50, 100, cellSeed + 3);
      } else if (riskRoll < 0.3) {
        forecast = stock + getRandomInt(10, 40, cellSeed + 3);
      } else {
        forecast = getRandomInt(0, stock, cellSeed + 3);
      }

      matrix[color][size] = { forecast, stock, orders };
    });
  });

  return matrix;
};

export const generateMockData = (count: number = 600): ArticleData[] => {
  const data: ArticleData[] = [];

  for (let i = 0; i < count; i++) {
    const seed = i * 12345;

    const numColors = getRandomInt(2, 5, seed + 1);
    const numSizes = getRandomInt(3, 6, seed + 2);

    const articleColors = [...COLORS]
      .sort((a, b) => seededRandom(seed + a.length) - 0.5)
      .slice(0, numColors);
    const articleSizes = [...SIZES]
      .sort((a, b) => seededRandom(seed + b.length) - 0.5)
      .slice(0, numSizes);
    articleSizes.sort((a, b) => SIZES.indexOf(a) - SIZES.indexOf(b));

    const cost = getRandomInt(10, 150, seed + 3);

    data.push({
      id: `SKU-${10000 + i}`,
      season: getRandomElement(SEASONS, seed + i),
      supplier: getRandomElement(SUPPLIERS, seed + 4),
      customer: getRandomElement(CUSTOMERS, seed + 5),
      family: getRandomElement(FAMILIES, seed + 6),
      theme: getRandomElement(THEMES, seed + 7),
      model: getRandomElement(MODELS, seed + 8),
      sizes: articleSizes,
      colors: articleColors,
      matrix: generateMatrix(articleColors, articleSizes, seed + 9),
      demandTrend: generateDemandTrend(seed + 10),
      cost: cost,
      price: Math.floor((cost * getRandomInt(15, 30, seed + 11)) / 10),
    });
  }

  return data;
};

export const mockArticles = generateMockData(600);
