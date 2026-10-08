---
title: keryx
description: Gives Claude Code a voice. After each reply, keryx says its gist out loud, locally, at no token cost.
hide:
  - navigation
  - toc
  - footer
---

<div class="hero" markdown>

# keryx

**Gives Claude Code a voice.**
{ .hero-subtitle }

<div class="hero-buttons" markdown>

[:octicons-rocket-24: Get started](getting-started.md){ .md-button .md-button--primary }
[:octicons-gear-24: Configuration](configuration.md){ .md-button }

</div>

<div class="hero-tagline" markdown>

<p class="hero-modes" markdown><span class="hero-chip">:octicons-cpu-24: Runs locally</span> <span class="hero-chip">:octicons-no-entry-24: Costs no tokens</span> <span class="hero-chip">:octicons-terminal-24: Claude Code plugin</span></p>

</div>

</div>

<div class="scroll-hint" aria-hidden="true">
  <div class="scroll-chevron"></div>
</div>

<section class="landing-section landing-section--intro">
  <div class="section-inner">
    <h2 class="section-title">What does keryx do?</h2>
    <p class="section-lead">After each reply, keryx says its gist out loud in one or two sentences: what happened, and what Claude needs from you. It also speaks permission prompts, and it stops talking when you send a new prompt. A local model writes the gist and a local voice speaks it, so nothing leaves your machine.</p>
  </div>
</section>

<section class="landing-section landing-section--herald">
  <div class="section-inner">
    <h2 class="section-title">From reply to speech</h2>
    <div class="pipeline-flow">
      <div class="pipeline-step">
        <span class="step-icon material-symbols-outlined">webhook</span>
        <span class="step-label">Hook</span>
        <span class="step-note">Stop hook sends the reply</span>
      </div>
      <span class="pipeline-arrow material-symbols-outlined" aria-hidden="true">arrow_forward</span>
      <div class="pipeline-step">
        <span class="step-icon material-symbols-outlined">memory</span>
        <span class="step-label">Daemon</span>
        <span class="step-note">One per machine, one queue</span>
      </div>
      <span class="pipeline-arrow material-symbols-outlined" aria-hidden="true">arrow_forward</span>
      <div class="pipeline-step">
        <span class="step-icon material-symbols-outlined">short_text</span>
        <span class="step-label">Shorten</span>
        <span class="step-note">Ollama gemma3:4b</span>
      </div>
      <span class="pipeline-arrow material-symbols-outlined" aria-hidden="true">arrow_forward</span>
      <div class="pipeline-step">
        <span class="step-icon material-symbols-outlined">record_voice_over</span>
        <span class="step-label">Speak</span>
        <span class="step-note">Kokoro-82M, GPU or CPU</span>
      </div>
      <span class="pipeline-arrow material-symbols-outlined" aria-hidden="true">arrow_forward</span>
      <div class="pipeline-step">
        <span class="step-icon material-symbols-outlined">volume_up</span>
        <span class="step-label">Play</span>
        <span class="step-note">Windows, through WSL2</span>
      </div>
    </div>
    <p class="pipeline-caption">A reply of 200 characters or fewer, once code, tables and paths are stripped, skips the shortening step and is spoken as written.</p>
  </div>
</section>

<section class="landing-section">
  <div class="section-inner">
    <h2 class="section-title">Explore</h2>
    <div class="feature-grid">
      <a href="getting-started/" class="feature-card" style="--card-accent: #3bc0cf">
        <span class="feature-icon material-symbols-outlined">rocket_launch</span>
        <div class="feature-name">Getting started</div>
        <p>Requirements, install and the first run.</p>
      </a>
      <a href="commands/" class="feature-card" style="--card-accent: #e0a526">
        <span class="feature-icon material-symbols-outlined">terminal</span>
        <div class="feature-name">Commands</div>
        <p>/keryx, replay and how to teach keryx a pronunciation.</p>
      </a>
      <a href="configuration/" class="feature-card" style="--card-accent: #3bc0cf">
        <span class="feature-icon material-symbols-outlined">tune</span>
        <div class="feature-name">Configuration</div>
        <p>Every setting, its default and its environment variable.</p>
      </a>
      <a href="architecture/" class="feature-card" style="--card-accent: #e0a526">
        <span class="feature-icon material-symbols-outlined">account_tree</span>
        <div class="feature-name">Architecture</div>
        <p>The daemon, the queue and the measurements behind each choice.</p>
      </a>
      <a href="troubleshooting/" class="feature-card" style="--card-accent: #3bc0cf">
        <span class="feature-icon material-symbols-outlined">build</span>
        <div class="feature-name">Troubleshooting</div>
        <p>What to check when keryx goes silent.</p>
      </a>
    </div>
  </div>
</section>

<section class="landing-section landing-section--herald" markdown>
  <div class="section-inner" markdown>

## Why "keryx" { .section-title }

<p class="section-lead" markdown>A <em>keryx</em> (<span class="greek">κῆρυξ</span>) was a herald in ancient Greece: the one who carried a message and announced it aloud, briefly, to the people it concerned.</p>

  </div>
</section>

<footer class="landing-footer">
  <span>2026 AJ Barea</span>
  <a href="https://github.com/ajbarea/keryx" aria-label="keryx on GitHub">
    <img src="assets/github.svg" alt="" width="18" height="18">
  </a>
</footer>
