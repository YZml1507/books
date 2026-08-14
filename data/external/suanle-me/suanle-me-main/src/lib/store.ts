"use client";

import { create } from "zustand";
import { persist } from "zustand/middleware";
import type { HistoryItem, ToolSlug } from "@/types";

type AppState = {
  theme: "dark" | "light";
  favorites: ToolSlug[];
  history: HistoryItem[];
  setTheme: (theme: "dark" | "light") => void;
  toggleFavorite: (slug: ToolSlug) => void;
  addHistory: (item: HistoryItem) => void;
  clearHistory: () => void;
};

export const useAppStore = create<AppState>()(
  persist(
    (set) => ({
      theme: "dark",
      favorites: [],
      history: [],
      setTheme: (theme) => set({ theme }),
      toggleFavorite: (slug) =>
        set((state) => ({
          favorites: state.favorites.includes(slug)
            ? state.favorites.filter((item) => item !== slug)
            : [...state.favorites, slug],
        })),
      addHistory: (item) =>
        set((state) => ({
          history: [item, ...state.history.filter((entry) => entry.id !== item.id)].slice(0, 30),
        })),
      clearHistory: () => set({ history: [] }),
    }),
    {
      name: "suanle-me-store",
      partialize: (state) => ({
        theme: state.theme,
        favorites: state.favorites,
        history: state.history,
      }),
    },
  ),
);
