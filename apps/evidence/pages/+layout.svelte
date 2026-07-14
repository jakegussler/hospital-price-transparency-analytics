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
	lightLogo="/brand/logo.svg"
	darkLogo="/brand/logo-dark.svg"
	homePageName="Overview"
	builtWithEvidence={false}
	{githubRepo}
>
	<div slot="content">
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
