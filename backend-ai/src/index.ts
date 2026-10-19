import express from "express";
import cors from "cors";
import articlesRouter from "./routes/articles";

const app = express();
const PORT = process.env.PORT || 4000;

app.use(cors({ origin: "http://localhost:3000" }));
app.use(express.json());

app.use("/api", articlesRouter);

app.get("/health", (_req, res) => {
  res.json({ status: "ok", service: "forcaster-backend" });
});

app.listen(PORT, () => {
  console.log(`Forcaster API running at http://localhost:${PORT}`);
  console.log(`  - GET /api/articles?season=SS2025&supplier=...`);
  console.log(`  - GET /api/filter-options?season=SS2025`);
});
