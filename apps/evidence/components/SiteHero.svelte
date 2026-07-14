<script>
	// Branded page hero (editorial style). Title renders as the page H1; body
	// content (value proposition, scope note) goes in the default slot.
	export let eyebrow = "";
	export let title = "";
</script>

<section class="hpl-hero">
	{#if eyebrow}
		<div class="hpl-hero-eyebrow">{eyebrow}</div>
	{/if}
	{#if title}
		<h1 class="hpl-hero-title">{title}</h1>
	{/if}
	<div class="hpl-hero-rule" aria-hidden="true"></div>
	<div class="hpl-hero-lead">
		<slot />
	</div>
</section>

<style>
	.hpl-hero {
		margin: 0.25rem 0 1.75rem 0;
		padding: 0.35rem 0 0.25rem 0;
	}
	.hpl-hero-eyebrow {
		font-size: 0.72rem;
		font-weight: 700;
		letter-spacing: 0.09em;
		text-transform: uppercase;
		color: #0f766e;
		margin-bottom: 0.4rem;
	}
	.hpl-hero-title {
		font-size: 1.95rem;
		font-weight: 800;
		line-height: 1.1;
		color: #0f172a;
		margin: 0 0 0.6rem 0;
		letter-spacing: -0.01em;
	}
	.hpl-hero-rule {
		width: 46px;
		height: 3px;
		background: #0f766e;
		border-radius: 2px;
		margin: 0 0 0.9rem 0;
	}
	.hpl-hero-lead {
		font-size: 1.02rem;
		line-height: 1.55;
		color: #334155;
		max-width: 62ch;
	}
	.hpl-hero-lead :global(p) {
		margin: 0.35rem 0;
	}
	.hpl-hero-lead :global(strong) {
		color: #0f766e;
	}
</style>
