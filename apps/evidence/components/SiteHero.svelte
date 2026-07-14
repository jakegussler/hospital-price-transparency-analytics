<script>
	// Branded page hero band. Title renders as the page H1; body content
	// (value proposition, scope note) goes in the default slot.
	export let eyebrow = "";
	export let title = "";
</script>

<section class="hpl-hero">
	<div class="hpl-hero-accent" aria-hidden="true"></div>
	<div class="hpl-hero-body">
		{#if eyebrow}
			<div class="hpl-hero-eyebrow">{eyebrow}</div>
		{/if}
		{#if title}
			<h1 class="hpl-hero-title">{title}</h1>
		{/if}
		<div class="hpl-hero-lead">
			<slot />
		</div>
	</div>
</section>

<style>
	.hpl-hero {
		position: relative;
		display: flex;
		gap: 1rem;
		margin: 0.25rem 0 1.5rem 0;
		padding: 1.5rem 1.6rem 1.5rem 1.4rem;
		border: 1px solid #ccfbf1;
		border-radius: 12px;
		background: linear-gradient(135deg, #f0fdfa 0%, #ffffff 62%);
		overflow: hidden;
	}
	.hpl-hero-accent {
		flex: 0 0 5px;
		border-radius: 4px;
		background: linear-gradient(180deg, #0f766e 0%, #0ea5e9 100%);
	}
	.hpl-hero-body {
		min-width: 0;
	}
	.hpl-hero-eyebrow {
		font-size: 0.72rem;
		font-weight: 700;
		letter-spacing: 0.09em;
		text-transform: uppercase;
		color: #0f766e;
		margin-bottom: 0.35rem;
	}
	.hpl-hero-title {
		font-size: 1.95rem;
		font-weight: 800;
		line-height: 1.1;
		color: #0f172a;
		margin: 0 0 0.5rem 0;
		letter-spacing: -0.01em;
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
