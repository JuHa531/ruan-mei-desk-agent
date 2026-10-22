# Token cost optimization

Measured with the Qwen3 tokenizer used by the `v10` adapter.

## Training data

| Item | Before (`v10`) | After (`story_economy_v11`) |
| --- | ---: | ---: |
| Samples | 154 | 223 |
| Total tokens | 133,718 | 73,112 |
| Repeated system tokens | 126,588 | 61,771 |
| Answer tokens | 3,424 | 5,221 |
| System share | 94.7% | 84.5% |

The economy set combines the original story dialogues, the contextual dialogues,
and curated situation-to-response examples. Each sample uses the compact
`TRAINING_SETTING` from `scripts/set_character.py`.

Build it with:

```powershell
python scripts\build_economy_training.py
```

The default output is `G:\ai\data\story_economy_v11.jsonl`.

## Runtime prompt

| Component | Before | After |
| --- | ---: | ---: |
| Full character prompt | 2,125 tokens | 718 tokens |
| Tool schema for ordinary chat | 4,046 tokens | 0 tokens |
| File work | 4,046 tokens | about 397 tokens |
| Music control | 4,046 tokens | about 380 tokens |
| PPT generation | 4,046 tokens | about 227 tokens |
| Typed error diagnosis | 4,046 tokens | about 573 tokens |

Tool schemas are selected from the current user intent by `select_tools()`.
Only matching groups are sent to Ollama.

Real Ollama `prompt_eval_count` after the change:

| Request | Prompt tokens |
| --- | ---: |
| Ordinary chat (`你好`) | 815 |
| File organization (`帮我整理文件夹`) | 1,370 |

## Context budget

`/api/agent` now computes the history budget from actual fixed costs:

```text
available history =
  context window
  - complete system prompt
  - selected tool schemas
  - output/tool reserve
```

This replaces the previous fixed 2,200-token reserve, which underestimated the
real prompt and tool overhead.

## Tool output

The UI may still display a longer tool result, but the model receives a compact
view capped around 700-1,400 characters depending on the tool. Error and
confirmation markers are preserved near the beginning.

Character-story retrieval is only injected for relevant questions and is capped
at 800 characters per turn.
