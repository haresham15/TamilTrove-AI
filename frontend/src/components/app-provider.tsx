"use client";

import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useRef,
  useState,
  type ReactNode,
} from "react";
import { ApiClientError, apiClient, isNetworkError } from "../lib/api-client";
import type {
  CollectionVisibility,
  Movie,
  MovieCollection,
  SearchFilters,
  SearchHistoryItem,
  SearchLanguage,
  UserPreferences,
  UserProfile,
} from "../types/api";

const STORAGE_KEY = "tamiltrove:v2:state";

export const DEFAULT_PREFERENCES: UserPreferences = {
  favoriteGenres: [],
  favoriteThemes: [],
  eraFrom: 2015,
  eraTo: 2026,
  hiddenGemPreference: 0.55,
  preferredLanguages: ["Tamil"],
  acceptsDubbed: false,
  analyticsConsent: false,
  onboardingMovieIds: [],
};

const DEFAULT_PRIVACY = {
  profileVisible: false,
  saveSearchHistory: true,
  personalizeRecommendations: true,
};

type Notice = {
  id: number;
  message: string;
  tone: "success" | "info" | "error";
};
type SessionMode = "anonymous" | "api" | "demo";

interface PersistedState {
  profile: UserProfile | null;
  watchlist: string[];
  liked: string[];
  dismissed: string[];
  ratings: Record<string, number>;
  viewed: string[];
  history: SearchHistoryItem[];
  collections: MovieCollection[];
}

interface AppContextValue extends PersistedState {
  hydrated: boolean;
  token: string | null;
  sessionMode: SessionMode;
  notice: Notice | null;
  notify: (message: string, tone?: Notice["tone"]) => void;
  signIn: (input: {
    email: string;
    password: string;
    displayName?: string;
    register?: boolean;
  }) => Promise<UserProfile>;
  signOut: () => Promise<void>;
  saveProfile: (changes: Partial<UserProfile>) => Promise<UserProfile>;
  toggleWatchlist: (movie: Movie) => void;
  toggleLike: (movie: Movie) => void;
  rateMovie: (movie: Movie, rating: number) => void;
  dismissMovie: (movie: Movie) => void;
  restoreDismissed: (movieId: string) => void;
  markViewed: (movie: Movie) => void;
  addSearchHistory: (
    query: string,
    language: SearchLanguage,
    resultCount: number,
    filters: SearchFilters,
  ) => void;
  clearSearchHistory: () => Promise<void>;
  resetTasteProfile: () => Promise<void>;
  deleteAccount: () => Promise<void>;
  createCollection: (
    name: string,
    description: string,
    visibility: CollectionVisibility,
  ) => Promise<MovieCollection>;
  updateCollection: (
    id: string,
    changes: Partial<
      Pick<MovieCollection, "name" | "description" | "visibility">
    >,
  ) => Promise<void>;
  deleteCollection: (id: string) => Promise<void>;
  addToCollection: (collectionId: string, movie: Movie) => Promise<void>;
  removeFromCollection: (
    collectionId: string,
    movieId: string,
  ) => Promise<void>;
  shareCollection: (id: string) => Promise<MovieCollection>;
}

const AppContext = createContext<AppContextValue | null>(null);

const initialState: PersistedState = {
  profile: null,
  watchlist: [],
  liked: [],
  dismissed: [],
  ratings: {},
  viewed: [],
  history: [],
  collections: [],
};

function localProfile(email: string, displayName?: string): UserProfile {
  const now = new Date().toISOString();
  return {
    id: `demo-${email.toLowerCase().replace(/[^a-z0-9]+/g, "-")}`,
    email,
    displayName:
      displayName?.trim() || email.split("@")[0] || "Cinema explorer",
    locale: "en-IN",
    onboardingComplete: false,
    isAdmin: email.toLowerCase() === "admin@tamiltrove.demo",
    preferences: { ...DEFAULT_PREFERENCES },
    privacy: { ...DEFAULT_PRIVACY },
    createdAt: now,
    updatedAt: now,
  };
}

function friendlyError(error: unknown): string {
  if (error instanceof ApiClientError) return error.message;
  if (error instanceof Error) return error.message;
  return "Something unexpected happened. Please try again.";
}

export function AppProvider({ children }: { children: ReactNode }) {
  const [state, setState] = useState<PersistedState>(initialState);
  const [token, setToken] = useState<string | null>(null);
  const [sessionMode, setSessionMode] = useState<SessionMode>("anonymous");
  const [hydrated, setHydrated] = useState(false);
  const [notice, setNotice] = useState<Notice | null>(null);
  const noticeId = useRef(0);

  const notify = useCallback(
    (message: string, tone: Notice["tone"] = "info") => {
      noticeId.current += 1;
      setNotice({ id: noticeId.current, message, tone });
    },
    [],
  );

  useEffect(() => {
    let cancelled = false;
    queueMicrotask(() => {
      if (cancelled) return;
      try {
        const stored = window.localStorage.getItem(STORAGE_KEY);
        if (stored) {
          const parsed = JSON.parse(stored) as Partial<PersistedState>;
          setState({
            ...initialState,
            ...parsed,
            ratings: parsed.ratings ?? {},
            profile: parsed.profile ?? null,
          });
          if (parsed.profile) setSessionMode("demo");
        }
      } catch {
        window.localStorage.removeItem(STORAGE_KEY);
      } finally {
        setHydrated(true);
      }
    });

    apiClient
      .profile()
      .then((profile) => {
        setState((current) => ({ ...current, profile }));
        setSessionMode("api");
      })
      .catch(() => undefined);
    return () => {
      cancelled = true;
    };
  }, []);

  useEffect(() => {
    if (!hydrated) return;
    window.localStorage.setItem(STORAGE_KEY, JSON.stringify(state));
  }, [hydrated, state]);

  useEffect(() => {
    if (!notice) return;
    const timer = window.setTimeout(() => setNotice(null), 4200);
    return () => window.clearTimeout(timer);
  }, [notice]);

  const signIn = useCallback(
    async ({
      email,
      password,
      displayName,
      register = false,
    }: Parameters<AppContextValue["signIn"]>[0]) => {
      try {
        const auth = register
          ? await apiClient.register(
              email,
              password,
              displayName || "Cinema explorer",
            )
          : await apiClient.login(email, password);
        setToken(auth.accessToken ?? null);
        setSessionMode("api");
        setState((current) => ({ ...current, profile: auth.profile }));
        notify(
          register
            ? "Your TamilTrove account is ready."
            : `Welcome back, ${auth.profile.displayName}.`,
          "success",
        );
        return auth.profile;
      } catch (error) {
        if (!isNetworkError(error)) throw error;
        const profile = localProfile(email, displayName);
        setToken(null);
        setSessionMode("demo");
        setState((current) => ({ ...current, profile }));
        notify(
          "Backend unavailable—continuing in private on-device demo mode.",
          "info",
        );
        return profile;
      }
    },
    [notify],
  );

  const signOut = useCallback(async () => {
    if (sessionMode === "api") {
      await apiClient.logout(token).catch(() => undefined);
    }
    setToken(null);
    setSessionMode("anonymous");
    setState(initialState);
    window.localStorage.removeItem(STORAGE_KEY);
    notify("You’re signed out.", "success");
  }, [notify, sessionMode, token]);

  const saveProfile = useCallback(
    async (changes: Partial<UserProfile>) => {
      const previous = state.profile;
      const optimistic: UserProfile = {
        ...(previous ?? localProfile("demo@tamiltrove.local")),
        ...changes,
        preferences: changes.preferences ??
          previous?.preferences ?? { ...DEFAULT_PREFERENCES },
        privacy: changes.privacy ?? previous?.privacy ?? { ...DEFAULT_PRIVACY },
        updatedAt: new Date().toISOString(),
      };
      setState((current) => ({ ...current, profile: optimistic }));

      if (sessionMode !== "api") {
        notify("Preferences saved on this device.", "success");
        return optimistic;
      }

      try {
        const saved = await apiClient.updateProfile(changes, token);
        setState((current) => ({ ...current, profile: saved }));
        notify("Profile changes saved.", "success");
        return saved;
      } catch (error) {
        if (isNetworkError(error)) {
          notify(
            "Offline for now—your changes are saved on this device.",
            "info",
          );
          return optimistic;
        }
        setState((current) => ({ ...current, profile: previous }));
        throw new Error(friendlyError(error));
      }
    },
    [notify, sessionMode, state.profile, token],
  );

  const toggleWatchlist = useCallback(
    (movie: Movie) => {
      const removing = state.watchlist.includes(movie.id);
      setState((current) => ({
        ...current,
        watchlist: removing
          ? current.watchlist.filter((id) => id !== movie.id)
          : [...current.watchlist, movie.id],
      }));
      notify(
        removing
          ? `Removed ${movie.title} from your watchlist.`
          : `Saved ${movie.title} to your watchlist.`,
        "success",
      );
      if (sessionMode === "api") {
        const operation = removing
          ? apiClient.removeWatchlist(movie.id, token)
          : apiClient.addWatchlist(movie.id, token);
        operation.catch((error) => {
          if (isNetworkError(error)) return;
          setState((current) => ({
            ...current,
            watchlist: removing
              ? [...current.watchlist, movie.id]
              : current.watchlist.filter((id) => id !== movie.id),
          }));
          notify(friendlyError(error), "error");
        });
      }
    },
    [notify, sessionMode, state.watchlist, token],
  );

  const toggleLike = useCallback(
    (movie: Movie) => {
      const removing = state.liked.includes(movie.id);
      setState((current) => ({
        ...current,
        liked: removing
          ? current.liked.filter((id) => id !== movie.id)
          : [...current.liked, movie.id],
      }));
      notify(
        removing
          ? `Removed your like for ${movie.title}.`
          : `${movie.title} will shape your recommendations.`,
        "success",
      );
      if (sessionMode === "api") {
        const operation = removing
          ? apiClient.deleteInteraction("like", movie.id, token)
          : apiClient.interaction(
              movie.id,
              "like",
              1,
              { surface: "web" },
              token,
            );
        operation.catch((error) => {
          if (!isNetworkError(error)) notify(friendlyError(error), "error");
        });
      }
    },
    [notify, sessionMode, state.liked, token],
  );

  const rateMovie = useCallback(
    (movie: Movie, rating: number) => {
      const value = Math.max(0, Math.min(5, rating));
      setState((current) => {
        const ratings = { ...current.ratings };
        if (value === 0) delete ratings[movie.id];
        else ratings[movie.id] = value;
        return { ...current, ratings };
      });
      notify(
        value
          ? `Rated ${movie.title} ${value} out of 5.`
          : `Cleared your rating for ${movie.title}.`,
        "success",
      );
      if (sessionMode === "api") {
        const operation = value
          ? apiClient.interaction(
              movie.id,
              "rating",
              value,
              { surface: "web" },
              token,
            )
          : apiClient.deleteInteraction("rating", movie.id, token);
        operation.catch((error) => {
          if (!isNetworkError(error)) notify(friendlyError(error), "error");
        });
      }
    },
    [notify, sessionMode, token],
  );

  const dismissMovie = useCallback(
    (movie: Movie) => {
      setState((current) => ({
        ...current,
        dismissed: current.dismissed.includes(movie.id)
          ? current.dismissed
          : [...current.dismissed, movie.id],
      }));
      notify(`${movie.title} hidden. You can restore it from Profile.`, "info");
      if (sessionMode === "api") {
        apiClient
          .interaction(movie.id, "dismiss", 1, { surface: "web" }, token)
          .catch((error) => {
            if (!isNetworkError(error)) notify(friendlyError(error), "error");
          });
      }
    },
    [notify, sessionMode, token],
  );

  const restoreDismissed = useCallback(
    (movieId: string) => {
      setState((current) => ({
        ...current,
        dismissed: current.dismissed.filter((id) => id !== movieId),
      }));
      if (sessionMode === "api") {
        apiClient
          .deleteInteraction("dismiss", movieId, token)
          .catch(() => undefined);
      }
      notify("Movie restored to your recommendations.", "success");
    },
    [notify, sessionMode, token],
  );

  const markViewed = useCallback(
    (movie: Movie) => {
      setState((current) => ({
        ...current,
        viewed: [
          movie.id,
          ...current.viewed.filter((id) => id !== movie.id),
        ].slice(0, 50),
      }));
      if (sessionMode === "api") {
        apiClient
          .interaction(
            movie.id,
            "viewed",
            1,
            { surface: "movie_detail" },
            token,
          )
          .catch(() => undefined);
      }
    },
    [sessionMode, token],
  );

  const addSearchHistory = useCallback(
    (
      query: string,
      detectedLanguage: SearchLanguage,
      resultCount: number,
      filters: SearchFilters,
    ) => {
      if (!query.trim() || state.profile?.privacy.saveSearchHistory === false)
        return;
      const item: SearchHistoryItem = {
        id: globalThis.crypto?.randomUUID?.() ?? `${Date.now()}`,
        query,
        detectedLanguage,
        resultCount,
        filters,
        createdAt: new Date().toISOString(),
      };
      setState((current) => ({
        ...current,
        history: [item, ...current.history].slice(0, 30),
      }));
    },
    [state.profile?.privacy.saveSearchHistory],
  );

  const clearSearchHistory = useCallback(async () => {
    setState((current) => ({ ...current, history: [] }));
    if (sessionMode === "api")
      await apiClient.clearSearchHistory(token).catch(() => undefined);
    notify("Search history cleared.", "success");
  }, [notify, sessionMode, token]);

  const resetTasteProfile = useCallback(async () => {
    setState((current) => ({
      ...current,
      liked: [],
      dismissed: [],
      ratings: {},
      viewed: [],
      profile: current.profile
        ? {
            ...current.profile,
            preferences: { ...DEFAULT_PREFERENCES },
            updatedAt: new Date().toISOString(),
          }
        : null,
    }));
    if (sessionMode === "api")
      await apiClient.resetInteractions(token).catch(() => undefined);
    notify(
      "Recommendation signals reset. Your watchlist and collections were kept.",
      "success",
    );
  }, [notify, sessionMode, token]);

  const deleteAccount = useCallback(async () => {
    if (sessionMode === "api") await apiClient.deleteProfile(token);
    setToken(null);
    setSessionMode("anonymous");
    setState(initialState);
    window.localStorage.removeItem(STORAGE_KEY);
  }, [sessionMode, token]);

  const createCollection = useCallback(
    async (
      name: string,
      description: string,
      visibility: CollectionVisibility,
    ) => {
      let collection: MovieCollection = {
        id: `local-${globalThis.crypto?.randomUUID?.() ?? Date.now()}`,
        ownerId: state.profile?.id,
        ownerDisplayName: state.profile?.displayName ?? "You",
        name: name.trim(),
        description: description.trim(),
        visibility,
        items: [],
        createdAt: new Date().toISOString(),
        updatedAt: new Date().toISOString(),
      };
      if (sessionMode === "api") {
        try {
          collection = await apiClient.createCollection(
            name,
            description,
            visibility,
            token,
          );
        } catch (error) {
          if (!isNetworkError(error)) throw new Error(friendlyError(error));
        }
      }
      setState((current) => ({
        ...current,
        collections: [collection, ...current.collections],
      }));
      notify(`Created “${collection.name}”.`, "success");
      return collection;
    },
    [notify, sessionMode, state.profile?.displayName, state.profile?.id, token],
  );

  const updateCollection = useCallback(
    async (
      id: string,
      changes: Partial<
        Pick<MovieCollection, "name" | "description" | "visibility">
      >,
    ) => {
      let updated: MovieCollection | undefined;
      if (sessionMode === "api") {
        try {
          updated = await apiClient.updateCollection(id, changes, token);
        } catch (error) {
          if (!isNetworkError(error)) throw new Error(friendlyError(error));
        }
      }
      setState((current) => ({
        ...current,
        collections: current.collections.map((collection) =>
          collection.id === id
            ? (updated ?? {
                ...collection,
                ...changes,
                updatedAt: new Date().toISOString(),
              })
            : collection,
        ),
      }));
      notify("Collection updated.", "success");
    },
    [notify, sessionMode, token],
  );

  const deleteCollection = useCallback(
    async (id: string) => {
      if (sessionMode === "api") {
        try {
          await apiClient.deleteCollection(id, token);
        } catch (error) {
          if (!isNetworkError(error)) throw new Error(friendlyError(error));
        }
      }
      setState((current) => ({
        ...current,
        collections: current.collections.filter((item) => item.id !== id),
      }));
      notify("Collection deleted.", "success");
    },
    [notify, sessionMode, token],
  );

  const addToCollection = useCallback(
    async (collectionId: string, movie: Movie) => {
      const collection = state.collections.find(
        (item) => item.id === collectionId,
      );
      if (
        !collection ||
        collection.items.some((item) => item.movieId === movie.id)
      ) {
        notify(
          collection
            ? `${movie.title} is already in that collection.`
            : "Collection not found.",
          "info",
        );
        return;
      }
      if (sessionMode === "api") {
        try {
          await apiClient.addCollectionItem(
            collectionId,
            movie.id,
            collection.items.length,
            token,
          );
        } catch (error) {
          if (!isNetworkError(error)) throw new Error(friendlyError(error));
        }
      }
      setState((current) => ({
        ...current,
        collections: current.collections.map((item) =>
          item.id === collectionId
            ? {
                ...item,
                items: [
                  ...item.items,
                  {
                    movieId: movie.id,
                    movie,
                    position: item.items.length,
                    addedAt: new Date().toISOString(),
                  },
                ],
              }
            : item,
        ),
      }));
      notify(`Added ${movie.title} to “${collection.name}”.`, "success");
    },
    [notify, sessionMode, state.collections, token],
  );

  const removeFromCollection = useCallback(
    async (collectionId: string, movieId: string) => {
      if (sessionMode === "api") {
        try {
          await apiClient.removeCollectionItem(collectionId, movieId, token);
        } catch (error) {
          if (!isNetworkError(error)) throw new Error(friendlyError(error));
        }
      }
      setState((current) => ({
        ...current,
        collections: current.collections.map((item) =>
          item.id === collectionId
            ? {
                ...item,
                items: item.items
                  .filter((entry) => entry.movieId !== movieId)
                  .map((entry, position) => ({ ...entry, position })),
              }
            : item,
        ),
      }));
      notify("Movie removed from collection.", "success");
    },
    [notify, sessionMode, token],
  );

  const shareCollection = useCallback(
    async (id: string) => {
      const local = state.collections.find((item) => item.id === id);
      if (!local) throw new Error("Collection not found.");
      let shared: MovieCollection = {
        ...local,
        visibility:
          local.visibility === "private"
            ? ("unlisted" as const)
            : local.visibility,
        shareToken: local.shareToken ?? id.replace(/^local-/, "share-"),
      };
      if (sessionMode === "api") {
        try {
          shared = await apiClient.shareCollection(id, token);
        } catch (error) {
          if (!isNetworkError(error)) throw new Error(friendlyError(error));
        }
      }
      setState((current) => ({
        ...current,
        collections: current.collections.map((item) =>
          item.id === id ? shared : item,
        ),
      }));
      return shared;
    },
    [sessionMode, state.collections, token],
  );

  const value = useMemo<AppContextValue>(
    () => ({
      ...state,
      hydrated,
      token,
      sessionMode,
      notice,
      notify,
      signIn,
      signOut,
      saveProfile,
      toggleWatchlist,
      toggleLike,
      rateMovie,
      dismissMovie,
      restoreDismissed,
      markViewed,
      addSearchHistory,
      clearSearchHistory,
      resetTasteProfile,
      deleteAccount,
      createCollection,
      updateCollection,
      deleteCollection,
      addToCollection,
      removeFromCollection,
      shareCollection,
    }),
    [
      state,
      hydrated,
      token,
      sessionMode,
      notice,
      notify,
      signIn,
      signOut,
      saveProfile,
      toggleWatchlist,
      toggleLike,
      rateMovie,
      dismissMovie,
      restoreDismissed,
      markViewed,
      addSearchHistory,
      clearSearchHistory,
      resetTasteProfile,
      deleteAccount,
      createCollection,
      updateCollection,
      deleteCollection,
      addToCollection,
      removeFromCollection,
      shareCollection,
    ],
  );

  return <AppContext.Provider value={value}>{children}</AppContext.Provider>;
}

export function useApp(): AppContextValue {
  const value = useContext(AppContext);
  if (!value) throw new Error("useApp must be used within AppProvider.");
  return value;
}
