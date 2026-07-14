<script>
	import '@evidence-dev/tailwind/fonts.css';
	import '../app.css';
	import { EvidenceDefaultLayout } from '@evidence-dev/core-components';
	export let data;

	// Brand / project links
	const githubRepo = 'https://github.com/jakegussler/hospital-price-transparency-analytics';
	const linkedin = 'https://www.linkedin.com/in/jakegussler'; // TODO: confirm exact LinkedIn URL
	const year = new Date().getFullYear();
</script>

<svelte:head>
	<!-- Cache-bust Evidence's default icon URLs so returning browsers pick up our brand. -->
	<link rel="icon" href="/favicon.ico?v=hpl-20260714" sizes="32x32" />
	<link rel="icon" href="/hospital-price-lens-icon.svg" type="image/svg+xml" />
	<link rel="apple-touch-icon" href="/apple-touch-icon.png?v=hpl-20260714" />
	<meta
		name="description"
		content="Hospital Price Lens organizes hospitals' published standard-charge files and shows when their prices can and cannot be compared. Currently covering the Nashville corpus."
	/>
	<meta property="og:type" content="website" />
	<meta property="og:site_name" content="Hospital Price Lens" />
	<meta property="og:title" content="Hospital Price Lens" />
	<meta
		property="og:description"
		content="Hospital prices you can actually compare — with the rules that limit those comparisons made explicit. Currently the Nashville corpus."
	/>
	<meta property="og:url" content="https://hospitalpricelens.com" />
	<meta property="og:image" content="https://hospitalpricelens.com/og-image.png" />
	<meta name="twitter:card" content="summary_large_image" />
	<meta name="twitter:title" content="Hospital Price Lens" />
	<meta
		name="twitter:description"
		content="Hospital prices you can actually compare — with the rules that limit those comparisons made explicit."
	/>
	<meta name="twitter:image" content="https://hospitalpricelens.com/og-image.png" />
	<meta name="theme-color" content="#0F766E" />
</svelte:head>

<EvidenceDefaultLayout
	{data}
	logo="/brand/logo.svg"
	lightLogo="/brand/logo.svg"
	darkLogo="/brand/logo-dark.svg"
	homePageName="Overview"
	builtWithEvidence={false}
	{githubRepo}
>
	<div slot="content" class="hpl-content">
		<slot />
		<footer class="hpl-footer">
			<span>© {year} Hospital Price Lens</span>
			<span class="sep">·</span>
			<span>An independent portfolio project by Jake Gussler</span>
			<span class="sep">·</span>
			<a href={githubRepo} target="_blank" rel="noopener noreferrer">GitHub</a>
			<span class="sep">·</span>
			<a href={linkedin} target="_blank" rel="noopener noreferrer">LinkedIn</a>
		</footer>
	</div>
</EvidenceDefaultLayout>

<style>
	/*
	 * Keep wide visualizations from enlarging the mobile layout viewport. Evidence
	 * tables remain horizontally scrollable inside their own .scrollbox.
	 */
	:global(html),
	:global(body) {
		width: 100%;
		max-width: 100%;
		overflow-x: hidden;
		overscroll-behavior-x: none;
	}

	:global(body) {
		position: relative;
	}

	@supports (overflow: clip) {
		:global(html),
		:global(body) {
			overflow-x: clip;
		}
	}

	:global(#evidence-main-article),
	.hpl-content,
	:global(#evidence-main-article .chart-container),
	:global(#evidence-main-article .table-container) {
		min-width: 0;
		max-width: 100%;
	}

	.hpl-content {
		width: 100%;
		overflow-x: hidden;
		overflow-wrap: anywhere;
	}

	:global(#evidence-main-article .scrollbox),
	:global(#evidence-main-article pre.markdown) {
		max-width: 100%;
		overflow-x: auto;
		overscroll-behavior-inline: contain;
	}

	.hpl-footer {
		margin-top: 3rem;
		padding: 1.25rem 0 0.5rem 0;
		border-top: 1px solid var(--grey-200, #e5e7eb);
		display: flex;
		flex-wrap: wrap;
		align-items: center;
		gap: 0.4rem;
		font-size: 0.8rem;
		line-height: 1.4;
		color: var(--grey-500, #64748b);
	}
	.hpl-footer a {
		color: #0f766e;
		font-weight: 600;
		text-decoration: none;
	}
	.hpl-footer a:hover {
		text-decoration: underline;
	}
	.hpl-footer .sep {
		opacity: 0.5;
	}
</style>
