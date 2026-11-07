<script lang="ts">
  let { region = "jp" }: { region?: string } = $props();
</script>

<header class="relative z-20 flex h-14 w-full items-center bg-neutral-900/90 px-5">
  <a class="text-xl font-semibold text-slate-100 hover:text-white" href={`/${region}/`}>
    Blue Archive
  </a>
</header>
