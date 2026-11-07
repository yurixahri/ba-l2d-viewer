<script lang="ts">
  let {
    value = $bindable(""),
    label = "",
    options = [],
    className = "",
  }: {
    value?: string;
    label?: string;
    options?: { value: string; label: string; disabled?: boolean }[];
    className?: string;
  } = $props();

  function update(event: Event) {
    value = (event.currentTarget as HTMLSelectElement).value;
  }
</script>

<label class={`grid gap-1.5 text-sm ${className}`}>
  {#if label}<span class="text-slate-300">{label}</span>{/if}
  <select
    class="h-10 w-full rounded-md border border-white/20 bg-slate-950 px-3 text-slate-100 outline-none focus:border-sky-400"
    {value}
    onchange={update}
  >
    {#each options as option}
      <option value={option.value} disabled={option.disabled}>{option.label}</option>
    {/each}
  </select>
</label>
