declare global {
  interface Window {
    wallpaperPropertyListener?: {
      applyUserProperties: (
        properties: Record<string, { value: unknown }>,
      ) => void;
      applyGeneralProperties: (
        properties: Record<string, { value: unknown }>,
      ) => void;
    };
  }
}

export {};
