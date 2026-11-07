<script lang="ts">
  let { image, title, href }: { image: string; title: string; href: string } = $props();
</script>

<a href={href} class="group relative m-4 grid h-48 w-48 place-items-center overflow-hidden rounded-xl shadow-xl transition hover:scale-105 xl:h-96 xl:w-96">
  <img src={image} alt="" class="absolute inset-0 h-full w-full object-cover transition group-hover:scale-110" />
  <span class="absolute inset-0 bg-black/60"></span>
  <span class="relative text-2xl font-semibold text-white xl:text-4xl">{title}</span>
</a>
