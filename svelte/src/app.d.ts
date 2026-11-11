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

declare module "howler" {
  export class Howl {
    constructor(options: any);
    play(id?: number): number;
    pause(id?: number): this;
    stop(id?: number): this;
    volume(vol?: number, id?: number): this | number;
    seek(seek?: number, id?: number): this | number;
    playing(id?: number): boolean;
    rate(rate?: number, id?: number): this | number;
    once(event: string, fn: () => void, id?: number): this;
    on(event: string, fn: () => void, id?: number): this;
    off(event: string, fn?: () => void, id?: number): this;
    unload(): void;
  }
}

export {};
