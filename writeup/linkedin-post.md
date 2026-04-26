<!--
LinkedIn FEED POST — short-form social. Paste body below into the LinkedIn
"Start a post" composer. Upload writeup/thumbnail.png separately when
LinkedIn shows the image picker. ~1,800 chars; under the 3,000 hard limit.

Long-form companion (LinkedIn Pulse / Medium import): writeup/linkedin-article.md
-->

I benchmarked 8 agent frameworks against the same model.

Most of them lost to 15 lines of code that just dump the input into a single prompt.

The default ReAct loop — the entrypoint shipping in LangChain, LangGraph, CrewAI, and most agent tutorials — scored 2 out of 15 on messy HTML extraction.

A single_shot baseline (no framework, one API call, no retry, no agent loop) scored 9 out of 15. In one-quarter the wall-clock. At roughly one-tenth the per-task cost at frontier-model list prices.

A few findings I didn't expect:

→ In one run, plan-and-execute fired the same non-existent CSS selector 417 times across 75 cells. The planner invented it. The executor had no feedback path.

→ Same matrix run twice on the same model at temperature 0 produced middle-of-the-pack rankings that swung by 0.33. seeds=1 evals are a coin flip.

→ At ~$2.50/M input + $10/M output, the elaborate plan-execute agent costs about $140k/year more than the baseline at 10k tasks/day — for a worse success rate.

→ On easy code-gen tasks (textbook algorithms with deterministic graders), every harness scored 15/15. The matrix collapsed from "which works?" to "which is wasteful?" — chain_of_thought 2x wall-clock, test_driven 6x tokens, same accuracy.

The honest claim: harness complexity pays returns only when your model's first-shot accuracy is below target AND the failures are multi-turn-recoverable. Both rarely hold at once on weak models.

Monday action: add a 15-line single_shot baseline to your eval harness. Make it the first row in your results table. If your production agent — whatever framework it's built on — doesn't beat it by more than 10%, rip out the production agent.

Most of the ceremony around modern agents is paid for a problem the model already solved in one call.

Full writeup with charts, the 8 cataloged patterns I haven't benchmarked yet, and the reproducible 150-run matrix:
github.com/jaafar-benabderrazak/harness-bench

What's the simplest baseline you've never bothered to measure?

#AgentEngineering #LLMOps #SoftwareEngineering #AIAgents
