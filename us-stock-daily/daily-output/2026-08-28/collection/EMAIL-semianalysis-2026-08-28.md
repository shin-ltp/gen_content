---
id: NWS-20260828-E005
category: news
ticker: 
title: OpenAI Jalapeño: Better Than Nvidia Blackwell
source: SemiAnalysis Newsletter（Gmail IMAP）
source_type: newsletter
url: gmail-imap://semianalysis/131141
relevance: us-stock
collected_at: 2026-08-28T07:35
collector: collect-email-imap
priority: TBD
newsletter_id: semianalysis
pub_date: 2026-08-28
assets_needed: []
assets_status: none
adopted: false
status: raw
---

## Body

OpenAI has spent the past couple years quietly building âJalapeÃ±o,â an inference chip just announced at Hot Chips. Rumors of a successful tapeout had been swirling for a while. But now we have details. OpenAI invited us to look at their chip, go to their labs to check out how real it is, and benchmark it with our InferenceX [ https://substack.com/redirect/460f4dc8-33f5-400d-8e05-9486c9ccc8df?j=eyJ1IjoiNHBrODFwIn0.ADkudvhjLis3O4hf0kyk1ZdQWZ3ekcj9HRLMuzwrT4w ] suite.
In June, OpenAI unveiled the chip program [ https://substack.com/redirect/e20a6bea-acc5-4103-a420-b61e164b3f35?j=eyJ1IjoiNHBrODFwIn0.ADkudvhjLis3O4hf0kyk1ZdQWZ3ekcj9HRLMuzwrT4w ] in partnership with Broadcom, built from a blank slate exclusively for LLM inference. Design work began in the middle of 2024 [ https://substack.com/redirect/99603fbf-e351-4dc8-a118-1a21cc26964e?j=eyJ1IjoiNHBrODFwIn0.ADkudvhjLis3O4hf0kyk1ZdQWZ3ekcj9HRLMuzwrT4w ], going from initial team hiring to manufacturing tape-out in ~16 months, an extremely fast ASIC development cycle.
In general first generation chips are not competitive, but OpenAI bucks the trend by being industry leading and beating every Nvidia, AMD, and Google chip we have been able to test on multiple top open source models. OpenAI does this with extreme hardware software codesign. Surprisingly, OpenAI is not over specialization on any specific part of model inference, but instead by focusing on being a general chip that delivers high performance in all scenarios.
In this article, we will go into architectural details, software details and performance results for JalapeÃ±o on InferenceX.
A generalized inference chip
Everyone says that OpenAIâs chip is specialized for OpenAI models, but thatâs wrong, OpenAI made a generalized chip for AI inference.
The timelines are insane. It shows that claims that use of AI is being used to accelerate chip design are real. Regardless of the quick timelines,Open AI spent a bunch of money, made pragmatic design decisions and their team is cracked, so this comes as no surprise.
Just looking at the specs, it is an immediate contender:
And the use of HBM4 makes it stand out as comparable to flagship GPUs from NVIDIA and AMD:
A lot of the media coverage of this chip has followed a few throwaway comments from OpenAI that claim the chip will be optimized for their models in a way that other chips are not. This is wrong. JalapeÃ±o is a generalized inference chip capable of running all sorts of models, and all sorts of workloads, including our benchmark InferenceX, where we ran the benchmark with OpenAI engineers in the lab. As a joke, OpenAI even showed us it running Doom, which was ported to their chip with just Codex prompts.
The following is our headline perf/W result, looking at token throughput per All-in utility MW. JalapeÃ±o smokes every other chip. All this is done without Multi Token Prediction (MTP), while the other chips on the chart are the best performing configs of each respective SKU, all with MTP.
JalapeÃ±o beats Blackwell on perf/W across almost all scenarios without being tuned for any specific point in the curve. It excels not only in low-latency scenarios but also in high-throughput scenarios. A more apples to apples comparison is against Single Token Prediction results, it knocks every competitor out of the water. At low concurrency scenarios, JalapeÃ±o demonstrates remarkable interactivity, hitting over 700 tokens per sec per user at concurrency 1 on the DeepSeek R1 model.
Incredibly, this is all achieved with single-token prediction (STP), no speculative decoding and no prefill-decode disaggregation. In addition to DeepSeek R1, we also got to see some other models, including Kimi-K2.5 and GPT-OSS which ran at approximately 1,400 tok/sec/user. For all models, we confirmed that JalapeÃ±oâs GSM8k evals attained results on par with Nvidia chips.
Some caveats on this. First, all numbers are provided to us by OpenAI. We verified the InferenceX runs in person in the lab, but we did not run the full suite of InferenceX [ https://substack.com/redirect/460f4dc8-33f5-400d-8e05-9486c9ccc8df?j=eyJ1IjoiNHBrODFwIn0.ADkudvhjLis3O4hf0kyk1ZdQWZ3ekcj9HRLMuzwrT4w ] benchmarks nor have we seen AgentX [ https://substack.com/redirect/3285b66f-1d40-4266-a4c3-8e46f062bab7?j=eyJ1IjoiNHBrODFwIn0.ADkudvhjLis3O4hf0kyk1ZdQWZ3ekcj9HRLMuzwrT4w ] results. AgentX is our preferred suite for comparing chip performance due to the datasetsâ long context and multi-turn characteristics that reflect the cache behavior of realistic production workflows. Frameworks that perform well on 8k1k may perform worse on AgentX as real production loads stress components like routers, prefix cache mechanisms, cache management, offload infrastructure, etc. These are not tested by single turn 8k1k. Read more about this in out AgentX article.
Second, we believe that comparison to Blackwell is somewhat incomplete and unfair. JalapeÃ±o is really competing against chips like Rubin that also use HBM4. Vera Rubin systems are starting to ship to customers right now, while it will still be some time before OpenAI has anything beyond engineering samples of JalapeÃ±o.
Thus, performance should really be compared against Rubin, not Blackwell, and in some sense we expect a custom chip like JalapeÃ±o to outperform Blackwell. Vera Rubin NVL72 delivers 5.4x the perf/MW of GB200 NVL72 as we described in our article analyzing the NVIDIA performance claims in their launch with CoreWeave last month [ https://substack.com/redirect/525949e7-dd51-45d2-9578-9be3a27b101d?j=eyJ1IjoiNHBrODFwIn0.ADkudvhjLis3O4hf0kyk1ZdQWZ3ekcj9HRLMuzwrT4w ]. We will compare JalapeÃ±o to Vera Rubinâs July performance figures later below.
Third, the models being tested are not on the open frontier. NVIDIA and AMD have published results on larger models such as DeepSeek V4 Pro and Kimi K3, using AgentX. The larger the model and the more recent the release, the more complicated it is to bring up on a new chip. With that said the models OpenAI has working on Jalapeno arenât exactly small either.
Performance Analysis
OpenAI designs for perf/W. The reason is simple: OpenAI is currently limited by datacenter power, not by budget or floorspace, and thus tokens per MW is paramount. At Computex 2026, Jensen said that perf/W, reliability and long lifetime are the core features of future GPUs. To quote: âIf you have 1 gigawatt of power, then throughput per watt is revenueâ. He also mentioned that choosing the wrong architecture just because the chips are cheaper doesnât make sense.
This was emphasized by Nvidia during the Vera talk at Hot Chips 2026 while showing the same revenue graph: âThe data center is power limited today.â Power matters and drives revenue.
Operators cannot simply obtain more MW because adding GPUs and adding grid capacity happen on very different timescales. Datacenter power envelopes have constraints such as their utility interconnection, infrastructure, cooling capacity, and UPS/backup-generation design. Grid delays repeatedly outpace hardware and construction timelines, driving the need for BtM (behind-the-meter) power capacity: gas turbines and on-site generators built and located at the data center itself. This capacity sits behind the utilityâs meter rather than being drawn from the public grid. It lets an operator power a facility without waiting on grid interconnection and utility upgrades, which is exactly why xAIâs Colossus 2 relies so heavily on BtM while its actual grid connection lags far behind. Find out more in our Energy model [ https://substack.com/redirect/c9da4e9c-5c79-4906-bda0-13741bae44ae?j=eyJ1IjoiNHBrODFwIn0.ADkudvhjLis3O4hf0kyk1ZdQWZ3ekcj9HRLMuzwrT4w ].
As we wrote in an X post, tok/s/MW reduces to tokens per joule since a watt is a joule per second. This makes tok/s/MW representative of a systemâs efficiency and ability to convert energy into tokens.
On this front, even when compared with Rubin, JalapeÃ±o wins. 
