<script>
  // Shared callout for the three standing note types used across the site:
  //   scope      - what the data covers (corpus, snapshot vintage)
  //   caution    - interpretation risks (what a number does NOT mean)
  //   definition - pointer to glossary/methodology definitions
  export let type = "scope";
  export let title = "";

  const styles = {
    scope: { border: "#0f766e", background: "#f0fdfa", text: "#0f766e", label: "Scope" },
    caution: { border: "#d97706", background: "#fffbeb", text: "#b45309", label: "Caution" },
    definition: { border: "#475569", background: "#f8fafc", text: "#475569", label: "Definition" },
  };

  $: style = styles[type] ?? styles.scope;
  $: heading = title || style.label;
</script>

<div
  class="hpt-callout"
  style={`border-left: 4px solid ${style.border}; background: ${style.background};`}
>
  <div class="hpt-callout-title" style={`color: ${style.text};`}>{heading}</div>
  <div class="hpt-callout-body">
    <slot />
  </div>
</div>

<style>
  .hpt-callout {
    border-radius: 4px;
    margin: 0.75rem 0 1rem 0;
    padding: 0.6rem 0.9rem;
  }
  .hpt-callout-title {
    font-size: 0.75rem;
    font-weight: 600;
    letter-spacing: 0.04em;
    text-transform: uppercase;
    margin-bottom: 0.15rem;
  }
  .hpt-callout-body {
    font-size: 0.9rem;
    line-height: 1.45;
  }
  .hpt-callout-body :global(p) {
    margin: 0.25rem 0;
  }
</style>
