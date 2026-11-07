<script lang="ts">
  import type { Snippet } from "svelte";

  let {
    variant = "default",
    type = "button",
    disabled = false,
    className = "",
    ariaLabel,
    onclick,
    children,
  }: {
    variant?: "default" | "outline" | "ghost";
    type?: "button" | "submit";
    disabled?: boolean;
    className?: string;
    ariaLabel?: string;
    onclick?: (event: MouseEvent) => void;
    children: Snippet;
  } = $props();

  let styleClass = $derived(
    variant === "outline"
      ? "border border-white/25 bg-black/20 hover:bg-white/10"
      : variant === "ghost"
        ? "bg-transparent hover:bg-white/10"
        : "bg-sky-500 text-slate-950 hover:bg-sky-400",
  );
</script>

<button {type} {disabled} aria-label={ariaLabel} {onclick} class={`inline-flex items-center justify-center rounded-md px-3 py-2 text-sm font-medium transition disabled:cursor-not-allowed disabled:opacity-50 ${styleClass} ${className}`}>
  {@render children()}
</button>
