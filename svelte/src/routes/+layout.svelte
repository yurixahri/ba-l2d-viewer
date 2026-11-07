<script lang="ts">
  import "../app.css";
  import type { Snippet } from "svelte";
  let { children }: { children: Snippet } = $props();
</script>

<svelte:head>
  <title>Blue Archive Resource Viewer</title>
  <meta name="description" content="Blue Archive resource viewer" />
</svelte:head>

<div class="fixed inset-0 -z-20 bg-cover bg-center blur-sm"
  style="background-image:url('/data/jp/MediaResources/Prologue/UIs/03_Scenario/01_Background/BG_CS_PR_01.jpg')"></div>
<div class="fixed inset-0 -z-10 bg-black/70"></div>
{@render children()}
