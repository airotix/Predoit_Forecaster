import { seasonsApi } from '@/lib/api/seasons';
import { create } from 'zustand';
import { persist } from 'zustand/middleware';
import {
  Season,
  SeasonStatus,
  ScenarioType,
  FinancialSummary,
  Alert,
  SeasonConfig,
} from '@/types';

interface SeasonState {
  activeSeason: Season | null;
  activeScenario: ScenarioType;
  financialSummary: FinancialSummary | null;
  alerts: Alert[];
  seasons: Season[];
  isLoading: boolean;
  error: string | null;

  // Actions
  setActiveSeason: (season: Season | null) => void;
  setActiveScenario: (scenario: ScenarioType) => void;
  setFinancialSummary: (summary: FinancialSummary | null) => void;
  setAlerts: (alerts: Alert[]) => void;
  dismissAlert: (alertId: string) => void;
  setSeasons: (seasons: Season[]) => void;
  createSeason: (config: SeasonConfig) => Promise<Season>;
  updateSeasonStatus: (seasonId: string, status: SeasonStatus) => void;
  setLoading: (loading: boolean) => void;
  setError: (error: string | null) => void;
  reset: () => void;
}

const initialState = {
  activeSeason: null,
  activeScenario: 'base' as ScenarioType,
  financialSummary: null,
  alerts: [],
  seasons: [],
  isLoading: false,
  error: null,
};

export const useSeasonStore = create<SeasonState>()(
  persist(
    // eslint-disable-next-line @typescript-eslint/no-unused-vars
    (set, _get) => ({
      ...initialState,

      setActiveSeason: (season) => {
        if(!season){set({activeSeason:null});return;}
        seasonsApi.activate(season.id).then(saved=>set({activeSeason:saved})).catch(error=>set({error:String(error)}));
      },

      setActiveScenario: (scenario) => set({ activeScenario: scenario }),

      setFinancialSummary: (summary) => set({ financialSummary: summary }),

      setAlerts: (alerts) => set({ alerts }),

      dismissAlert: (alertId) =>
        set((state) => ({
          alerts: state.alerts.map((a) =>
            a.id === alertId ? { ...a, dismissed: true } : a
          ),
        })),

      setSeasons: (seasons) => set({ seasons }),

      createSeason: async (config: SeasonConfig) => {
        const newSeason = await seasonsApi.create(config);
        set((state) => ({
          seasons: [...state.seasons, newSeason],
          activeSeason: newSeason,
        }));
        return newSeason;
      },

      updateSeasonStatus: (seasonId, status) =>
        set((state) => ({
          seasons: state.seasons.map((s) =>
            s.id === seasonId ? { ...s, status, updatedAt: new Date().toISOString() } : s
          ),
          activeSeason:
            state.activeSeason?.id === seasonId
              ? { ...state.activeSeason, status, updatedAt: new Date().toISOString() }
              : state.activeSeason,
        })),

      setLoading: (loading) => set({ isLoading: loading }),

      setError: (error) => set({ error }),

      reset: () => set(initialState),
    }),
    {
      name: 'season-store',
      partialize: (state) => ({
        activeSeason: state.activeSeason,
        activeScenario: state.activeScenario,
        seasons: state.seasons,
      }),
    }
  )
);
