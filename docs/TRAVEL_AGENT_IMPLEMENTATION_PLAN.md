# Travel Agent Foundry Demo --- Iterative Implementation Plan

## Purpose

Build a travel-planning demo agent that showcases Microsoft Foundry tool
integration using only Foundry-supported tool types. The first version helps a
traveller decide whether a destination and date range are a good time to visit by
combining weather forecasts, web research and personal travel reviews.

The demo should prioritize reliable tool orchestration over full booking. Actual
booking, payment or reservation actions are intentionally out of scope for early
iterations.

## Agent Concept

Working name: **TravelAgent**

Example request:

> "I am thinking of visiting Lisbon for four nights between 10 and 20 October.
> Check the weather, look for recent travel advice or blog posts, compare that
> with my saved reviews, and tell me whether it is a good time to go."

The agent should return:

-   a clear go / wait / adjust-dates recommendation
-   best-fit dates inside the requested travel window
-   weather summary and confidence
-   web research themes such as seasonality, events, crowds or closures
-   relevant personal preference signals from prior reviews
-   risks and follow-up checks before booking
-   sources/tools used for each major conclusion

## Foundry Tool Scope

Use Foundry-supported tools only:

-   OpenAPI for hosted weather and destination data APIs
-   Web search for current travel context and blog-style information
-   Foundry IQ or file-search-backed retrieval for personal reviews, travel
    preferences and saved notes
-   Code interpreter for scoring, comparison and CSV analysis
-   Model Context Protocol (MCP) for optional later stateful or custom tools
-   Agent-to-agent (A2A) only after the single-agent flow is stable
-   Browser automation only if a useful travel source has no API or searchable
    representation

Arbitrary hosted services should be integrated through OpenAPI or MCP rather than
treated as unsupported direct REST tools.

## Target End State

The final demo agent can handle a request such as:

> "Compare Lisbon, Porto and Seville for a five-day solo trip in late October.
> Use forecast data, current web results and my personal travel reviews. Pick the
> best destination, explain the trade-offs, and prepare a booking-readiness
> checklist."

The final system combines:

-   Foundry toolbox with multiple tool types
-   OpenAPI weather and location lookup
-   Foundry web search
-   Foundry IQ or file-search-backed retrieval over personal travel notes
-   Code interpreter scoring and comparison
-   optional MCP tool for saving a trip brief or creating a task
-   explicit approval boundaries for state-changing actions
-   trace-based debugging
-   evaluation cases for tool choice, grounding and recommendation quality

## Development Principle

Build as vertical slices. Every iteration should leave a working demo, add or
extend evaluation coverage, and preserve enough traces to identify failures.

Each increment follows this loop:

1.  Define one new travel-planning behaviour.
2.  Add or extend evaluation cases.
3.  Implement the smallest tool or agent change that satisfies it.
4.  Run local smoke tests where possible.
5.  Run agent evaluations.
6.  Inspect traces for tool-selection, argument, retrieval or synthesis errors.
7.  Fix the responsible layer rather than only changing the prompt.
8.  Add newly discovered failure modes to the evaluation dataset.

## Toolbox Evolution Strategy

Grow the Foundry toolbox one capability at a time. Do not front-load the most
complex final toolbox.

The toolbox creation script should evolve by iteration:

1.  Start with web search only.
2.  Add the OpenAPI weather/location tool once the web-search behaviour is
    stable.
3.  Add Foundry IQ or file-search-backed personal review retrieval once weather
    integration is stable.
4.  Add code interpreter when scoring needs repeatable calculations.
5.  Add MCP or authenticated APIs only after the read-only travel flow is stable.

Each toolbox change should create or update a new toolbox version only when the
tool definition has materially changed. The script should print the toolbox name,
version and MCP endpoint so the agent configuration can be verified after each
iteration.

## Proposed Demo Data

Seed Foundry IQ or file-search-backed retrieval with small markdown files that
represent personal travel memory:

```text
travel-reviews/
├── travel-preferences.md
├── lisbon-2023.md
├── barcelona-2024.md
├── porto-2024.md
├── seville-2025.md
└── tokyo-2025.md
```

Example review content:

```markdown
# Lisbon, October 2023

Stayed near Principe Real. Loved walkable neighbourhoods, viewpoints, cooler
evenings, food markets and short transfers. Avoided overly packed tourist zones.

Good fit when daytime temperatures were 18-24C. Rain was acceptable when there
were indoor food and culture options.
```

## Iteration 0 --- Baseline Agent and Evaluation Harness

Create a minimal hosted Foundry agent with instructions for travel timing advice.
No external tools are required in this first slice.

Initial behaviours:

-   ask clarifying questions when the destination or travel window is missing
-   avoid pretending to have live weather or current web knowledge without tools
-   produce a structured recommendation template when enough information is
    present

Example evaluation cases:

```json
{
  "input": "Is October a good time to visit Lisbon?",
  "expected_behavior": "asks for approximate travel dates or explains limits without live tools",
  "forbidden_claims": ["live forecast", "current events"]
}
```

Trace failure categories:

-   tool selection
-   missing clarification
-   unsupported factual claim
-   retrieval grounding
-   scoring/calculation
-   recommendation quality
-   action approval

**Exit criterion:** the agent gives honest baseline travel advice and evaluation
can identify unsupported claims.

## Iteration 1 --- Current Context with Web Search

Add Foundry web search as the first toolbox capability. This gives the demo an
immediate hosted tool without requiring custom OpenAPI specifications, personal
corpus setup or authentication.

Search targets:

-   seasonal travel advice
-   recent blog posts
-   crowding and closures
-   local events
-   transport disruption or major public holidays

Example prompt:

> "Use current web results to check whether late October is a good time to visit
> Lisbon, especially for crowds and events."

Evaluation coverage:

-   uses web search for current or blog-style context
-   distinguishes retrieved current context from general model knowledge
-   avoids over-weighting a single source
-   flags uncertainty when sources disagree
-   does not cite web content that was not retrieved

**Exit criterion:** the agent can use web search to produce a grounded current
travel-context summary.

## Iteration 2 --- Weather Forecast via OpenAPI

Add an OpenAPI tool for a hosted weather API. Open-Meteo is the preferred first
candidate because it is free and does not require an API key.

Recommended operations:

-   `geocode_location`: resolve a city/place name to latitude and longitude
-   `get_daily_forecast`: get daily temperature, precipitation and wind for a
    date range

Keep the OpenAPI document small and explicit. Tool descriptions should explain
when to call each operation and what each input means.

Example prompt:

> "Check the forecast for Lisbon from 10 to 14 October and tell me if it looks
> comfortable for walking."

Evaluation coverage:

-   calls geocoding before forecast when coordinates are unknown
-   passes the requested date range correctly
-   handles unsupported or ambiguous places
-   does not infer weather when the API fails
-   summarizes temperature and rain risk accurately

**Exit criterion:** the agent reliably uses OpenAPI weather data for destination
timing advice.

## Iteration 3 --- Personal Reviews with Foundry IQ

Add Foundry IQ or file-search-backed retrieval over personal travel reviews and
preference notes. This should happen after web search and OpenAPI are working so
the review corpus can be introduced as an additional grounding source rather
than the first complex integration.

Initial capabilities:

-   find prior reviews for a destination
-   infer stable traveller preferences from review notes
-   compare a proposed destination with those preferences
-   quote or cite the relevant review evidence in the answer

Example prompt:

> "Would Lisbon in October fit my usual travel preferences? Use my travel
> reviews as evidence."

Evaluation coverage:

-   retrieves the Lisbon review when asked about Lisbon
-   retrieves general preferences when no exact destination review exists
-   does not invent preferences absent from the files
-   distinguishes positive preference signals from warnings
-   separates personal-review evidence from web-search evidence

**Exit criterion:** the agent grounds preference analysis in personal-review
retrieval evidence and can combine it with web and weather evidence.

## Iteration 4 --- Scoring with Code Interpreter

Add code interpreter for lightweight scoring and comparison.

Initial scoring dimensions:

-   temperature comfort
-   rain risk
-   wind risk
-   fit to personal preferences
-   web-context risk

The score is an explanation aid, not a hidden authority. The agent should show
the major factors behind the score.

Example prompt:

> "Score Lisbon from 1 to 10 for my preferred travel style using the forecast,
> my reviews and current travel context."

Evaluation coverage:

-   code interpreter receives structured inputs rather than raw prompt text only
-   score changes when weather or preference evidence changes
-   score explanation matches the computed factors
-   no false precision when data is incomplete

**Exit criterion:** the agent produces repeatable, explainable destination-fit
scores.

## Iteration 5 --- Multi-Destination Comparison

Extend the agent to compare two or more destinations for the same date range.

Example prompt:

> "Compare Lisbon, Porto and Seville for a four-night trip between 10 and 20
> October. Pick the best option for my preferences."

Expected behaviour:

-   retrieve weather for each destination
-   run web search for relevant context per destination
-   retrieve personal reviews or general preferences
-   score each destination consistently
-   recommend one destination with trade-offs

Evaluation coverage:

-   all requested destinations are considered
-   no destination receives fabricated data when a tool call fails
-   ranking is supported by the evidence
-   answer includes a concise comparison table

**Exit criterion:** the agent can rank multiple destinations from heterogeneous
tool evidence.

## Iteration 6 --- Booking-Readiness Checklist

Add checklist generation without booking or payment.

Checklist sections:

-   best travel dates
-   accommodation area suggestions
-   transport checks
-   weather packing notes
-   reservations to consider
-   open questions before booking
-   risks to re-check 48 hours before travel

Example prompt:

> "Create a booking-readiness checklist for the recommended Lisbon trip."

Evaluation coverage:

-   checklist reflects the selected destination and dates
-   does not claim reservations have been made
-   highlights missing data needed before booking
-   separates recommendations from actions

**Exit criterion:** the agent can prepare a practical pre-booking artifact while
remaining read-only.

## Iteration 7 --- Optional MCP Action Tool

Add an MCP server only after the read-only experience is stable. The MCP server
should perform a small, low-risk action such as saving a trip brief, creating a
task, or creating a planning note.

Candidate MCP tools:

-   `save_trip_brief`
-   `create_packing_task`
-   `create_booking_checklist`

Approval policy:

-   the agent may draft the content of a note or task
-   the agent must ask for explicit user approval before creating or updating
    external state
-   the agent must show the exact title/body/action before calling the MCP tool

Example prompt:

> "Save this Lisbon recommendation as a trip planning note."

Evaluation coverage:

-   no state-changing MCP call occurs without approval
-   approved action sends the expected title/body
-   duplicate approvals are handled idempotently where possible
-   tool failures are reported without pretending the note was saved

**Exit criterion:** the demo includes a controlled state-changing action with a
clear human-in-the-loop boundary.

## Iteration 8 --- Optional Travel Data API with Auth

If a stronger auth demonstration is needed, add a second OpenAPI service that
requires API-key or OAuth-style authentication.

Possible candidates:

-   travel points-of-interest API with a free tier
-   events API with a free tier
-   geocoding or places API with API-key authentication
-   a small hosted wrapper around a public API

The value of this iteration is showing Foundry connections/auth rather than
expanding the travel experience at all costs.

Evaluation coverage:

-   credential is represented through connection configuration, not prompts
-   secrets never appear in traces or final answers
-   expired or missing credentials produce a clear user-facing explanation
-   business behaviour remains stable after adding auth

**Exit criterion:** the toolbox demonstrates at least one authenticated OpenAPI
integration safely.

## Iteration 9 --- Optional Agent-to-Agent Demo

Split responsibilities only if the single-agent demo is stable.

Candidate agents:

-   Research Agent: web search and travel context
-   Weather Analyst Agent: weather lookup and scoring
-   Preference Agent: Foundry IQ or file-search-backed analysis over personal
    reviews
-   Planner Agent: final synthesis and checklist

Example prompt:

> "Use specialist agents to compare Lisbon, Porto and Seville for my late
> October trip."

Evaluation coverage:

-   delegation is used only when it improves clarity
-   sub-agent outputs are traceable
-   final answer reconciles conflicting specialist recommendations
-   total latency remains acceptable for a demo

**Exit criterion:** A2A adds demonstrable value rather than architectural noise.

## Suggested Evaluation Dataset

Start with 10-15 stable cases:

-   missing destination asks a clarifying question
-   missing dates asks a clarifying question
-   current-context request calls web search
-   weather request calls OpenAPI with correct dates
-   weather API failure is handled honestly
-   known destination retrieves matching personal review
-   unknown destination falls back to general preferences
-   multi-destination request ranks every destination
-   rainy forecast lowers score for walking-heavy preference
-   mild forecast raises score for walking-heavy preference
-   checklist request stays read-only
-   save-note request asks for approval before MCP action
-   approved save-note request calls MCP tool once

## Demo Script

1.  Ask: "Use recent web results to tell me whether Lisbon is a good destination
    in mid-October."
2.  Show web search as the first toolbox capability.
3.  Ask: "Check the actual forecast for Lisbon from 10-14 October."
4.  Show OpenAPI geocoding and weather calls added to the toolbox.
5.  Ask: "Now compare that with my personal travel reviews and preferences."
6.  Show Foundry IQ or file-search-backed review evidence integrated with web and
    weather findings.
7.  Ask: "Compare Lisbon, Porto and Seville."
8.  Show code-interpreter scoring and ranking.
9.  Ask: "Create a booking-readiness checklist."
10. Optional: approve saving the checklist through MCP.

## Non-Goals

-   making real bookings
-   taking payment
-   scraping websites when web search or APIs are sufficient
-   presenting travel advice as guaranteed or complete
-   storing real sensitive travel documents in the demo corpus
-   relying on local-only endpoints for hosted Foundry toolbox tools

## Open Questions

-   Which destinations should be included in the first demo dataset?
-   Should personal reviews be synthetic, real, or a mix?
-   Is the first hosted OpenAPI tool direct Open-Meteo, or a small wrapper with a
    stricter OpenAPI document?
-   Should the optional MCP action save to GitHub issues, a markdown note store,
    a calendar/task system, or a purpose-built demo service?
-   Is authenticated API integration required for the first public demo, or can it
    wait until the web-search, weather and Foundry IQ flow is stable?