window.BENCHMARK_DATA = {
  "lastUpdate": 1792330194655,
  "repoUrl": "https://github.com/Arete-Consortium/animus",
  "entries": {
    "Benchmark": [
      {
        "commit": {
          "author": {
            "email": "AreteDriver@gmail.com",
            "name": "James C. Young",
            "username": "AreteDriver"
          },
          "committer": {
            "email": "noreply@github.com",
            "name": "GitHub",
            "username": "web-flow"
          },
          "distinct": true,
          "id": "bed4d6539266a420aeedba028d0c3592db6dc1b3",
          "message": "Merge pull request #133 from Arete-Consortium/codex/hunter-os-ci-repair\n\nfeat(hunter-os): add scoped repository and retire Core Chroma",
          "timestamp": "2026-10-17T20:35:29-07:00",
          "tree_id": "d390a49eef15e66bad0dc45c2b6bfe0f9e1541cc",
          "url": "https://github.com/Arete-Consortium/animus/commit/bed4d6539266a420aeedba028d0c3592db6dc1b3"
        },
        "date": 1792295662685,
        "tool": "pytest",
        "benches": [
          {
            "name": "tests/test_benchmarks.py::TestMemorySerdeBenchmark::test_memory_serde_500",
            "value": 302.5608147263543,
            "unit": "iter/sec",
            "range": "stddev: 0.00004595378118216035",
            "extra": "mean: 3.3051206611286794 msec\nrounds: 301"
          },
          {
            "name": "tests/test_benchmarks.py::TestConversationSerdeBenchmark::test_conversation_serde_50msg",
            "value": 719.5325466052012,
            "unit": "iter/sec",
            "range": "stddev: 0.000014437441089091705",
            "extra": "mean: 1.3897911980744464 msec\nrounds: 727"
          },
          {
            "name": "tests/test_benchmarks.py::TestDetectModeBenchmark::test_detect_mode_1000",
            "value": 223.3623610082891,
            "unit": "iter/sec",
            "range": "stddev: 0.00002920093186036299",
            "extra": "mean: 4.477030039823449 msec\nrounds: 226"
          },
          {
            "name": "tests/test_benchmarks.py::TestEntitySearchBenchmark::test_entity_search_200",
            "value": 1889.3921325368715,
            "unit": "iter/sec",
            "range": "stddev: 0.000009348520825831526",
            "extra": "mean: 529.2707547465587 usec\nrounds: 1949"
          },
          {
            "name": "tests/test_benchmarks.py::TestLocalSearchBenchmark::test_local_search_500",
            "value": 3398.656066454863,
            "unit": "iter/sec",
            "range": "stddev: 0.000006634746367908761",
            "extra": "mean: 294.2339502576086 usec\nrounds: 3498"
          },
          {
            "name": "tests/test_benchmarks.py::TestWorkflowParseBenchmark::test_parse_20_step_workflow",
            "value": 16927.762785114584,
            "unit": "iter/sec",
            "range": "stddev: 0.0000027485447744128786",
            "extra": "mean: 59.07455182910227 usec\nrounds: 17384"
          },
          {
            "name": "tests/test_benchmarks.py::TestYAMLLoadBenchmark::test_load_yaml_10_steps",
            "value": 383.74104464957634,
            "unit": "iter/sec",
            "range": "stddev: 0.000027061055634575825",
            "extra": "mean: 2.60592400511438 msec\nrounds: 391"
          },
          {
            "name": "tests/test_benchmarks.py::TestConditionEvalBenchmark::test_condition_evaluate_1000",
            "value": 4738.354593481558,
            "unit": "iter/sec",
            "range": "stddev: 0.000005394070786906425",
            "extra": "mean: 211.04372420242169 usec\nrounds: 4797"
          },
          {
            "name": "tests/test_benchmarks.py::TestCacheBenchmark::test_cache_set_get_1000",
            "value": 36.84152609599762,
            "unit": "iter/sec",
            "range": "stddev: 0.0007152007500654405",
            "extra": "mean: 27.14328384210549 msec\nrounds: 38"
          },
          {
            "name": "tests/test_benchmarks.py::TestTaskStoreBenchmark::test_record_query_100",
            "value": 14.660965380822427,
            "unit": "iter/sec",
            "range": "stddev: 0.0018049469812146438",
            "extra": "mean: 68.20833239999804 msec\nrounds: 15"
          },
          {
            "name": "tests/test_benchmarks.py::TestBudgetBenchmark::test_budget_record_usage_500",
            "value": 549.0993074543183,
            "unit": "iter/sec",
            "range": "stddev: 0.000023891748488771284",
            "extra": "mean: 1.8211641982141709 msec\nrounds: 560"
          },
          {
            "name": "tests/test_benchmarks.py::TestCheckpointBenchmark::test_checkpoint_lifecycle_20",
            "value": 66.07251961550669,
            "unit": "iter/sec",
            "range": "stddev: 0.0005754911204635744",
            "extra": "mean: 15.134885211268802 msec\nrounds: 71"
          },
          {
            "name": "tests/test_benchmarks.py::TestSkillLookupBenchmark::test_skill_lookup_100",
            "value": 10437.047716952484,
            "unit": "iter/sec",
            "range": "stddev: 0.000003815805103678929",
            "extra": "mean: 95.8125350309302 usec\nrounds: 10605"
          },
          {
            "name": "tests/test_benchmarks.py::TestSessionControllerBenchmark::test_policy_check_latency",
            "value": 1397252.3537114775,
            "unit": "iter/sec",
            "range": "stddev: 9.581629182508286e-8",
            "extra": "mean: 715.6903313447507 nsec\nrounds: 143267"
          },
          {
            "name": "tests/test_benchmarks.py::TestSessionControllerBenchmark::test_event_log_throughput",
            "value": 6128.607449085755,
            "unit": "iter/sec",
            "range": "stddev: 0.000006804562451880806",
            "extra": "mean: 163.1692041475387 usec\nrounds: 6510"
          },
          {
            "name": "tests/test_benchmarks.py::TestCheckpointBenchmark::test_checkpoint_save_latency",
            "value": 1397.5767847592317,
            "unit": "iter/sec",
            "range": "stddev: 0.00004599369015890168",
            "extra": "mean: 715.5241922341143 usec\nrounds: 1571"
          },
          {
            "name": "tests/test_benchmarks.py::TestCheckpointBenchmark::test_checkpoint_load_latency",
            "value": 6234.203021828748,
            "unit": "iter/sec",
            "range": "stddev: 0.000011005893489175835",
            "extra": "mean: 160.405427365543 usec\nrounds: 6870"
          },
          {
            "name": "tests/test_benchmarks.py::TestCheckpointBenchmark::test_checkpoint_list_recent",
            "value": 5387.155012935636,
            "unit": "iter/sec",
            "range": "stddev: 0.000010641656970375066",
            "extra": "mean: 185.62673574434007 usec\nrounds: 5752"
          },
          {
            "name": "tests/test_benchmarks.py::TestContextManagerBenchmark::test_finalize_summary_latency",
            "value": 266790.2231204555,
            "unit": "iter/sec",
            "range": "stddev: 4.327964019214371e-7",
            "extra": "mean: 3.7482632920491286 usec\nrounds: 138485"
          },
          {
            "name": "tests/test_benchmarks.py::TestResolverBenchmark::test_resolve_50_intents",
            "value": 708.6737109983488,
            "unit": "iter/sec",
            "range": "stddev: 0.00004487370920495445",
            "extra": "mean: 1.4110866319441189 msec\nrounds: 720"
          },
          {
            "name": "tests/test_benchmarks.py::TestStructuralOverlapBenchmark::test_structural_overlaps_1000",
            "value": 290.65461980446065,
            "unit": "iter/sec",
            "range": "stddev: 0.00013392367128772838",
            "extra": "mean: 3.4405095665527528 msec\nrounds: 293"
          },
          {
            "name": "tests/test_benchmarks.py::TestConstraintBenchmark::test_validate_20_constraints",
            "value": 193411.73062980958,
            "unit": "iter/sec",
            "range": "stddev: 7.30482581735103e-7",
            "extra": "mean: 5.170317212630716 usec\nrounds: 187688"
          },
          {
            "name": "tests/test_benchmarks.py::TestPhiScoringBenchmark::test_phi_score_100_outcomes",
            "value": 86438.87611026915,
            "unit": "iter/sec",
            "range": "stddev: 0.000001104236774816446",
            "extra": "mean: 11.568868604033106 usec\nrounds: 86304"
          },
          {
            "name": "tests/test_benchmarks.py::TestRealisticScenarioBenchmark::test_realistic_25_agents",
            "value": 218.29719194861133,
            "unit": "iter/sec",
            "range": "stddev: 0.000033785085726764625",
            "extra": "mean: 4.58091096396424 msec\nrounds: 222"
          },
          {
            "name": "tests/test_benchmarks.py::TestPublishThroughputBenchmark::test_publish_100_intents",
            "value": 871.2532600607844,
            "unit": "iter/sec",
            "range": "stddev: 0.000024668861125581766",
            "extra": "mean: 1.147771888888236 msec\nrounds: 891"
          }
        ]
      },
      {
        "commit": {
          "author": {
            "email": "AreteDriver@gmail.com",
            "name": "James C. Young",
            "username": "AreteDriver"
          },
          "committer": {
            "email": "noreply@github.com",
            "name": "GitHub",
            "username": "web-flow"
          },
          "distinct": true,
          "id": "fb3e5a10d5af585a433225665344f6290dc71eab",
          "message": "fix(pwa): upgrade Vitest past CVE-2026-84373 (#142)\n\n* fix(pwa): upgrade Vitest past CVE-2026-84373\n\n* ci(pwa): use npm 10 compatible peer resolution",
          "timestamp": "2026-10-18T06:11:43-07:00",
          "tree_id": "147c29f844320ddb5ec6fe454e70a51d30f588b7",
          "url": "https://github.com/Arete-Consortium/animus/commit/fb3e5a10d5af585a433225665344f6290dc71eab"
        },
        "date": 1792330193907,
        "tool": "pytest",
        "benches": [
          {
            "name": "tests/test_benchmarks.py::TestMemorySerdeBenchmark::test_memory_serde_500",
            "value": 297.98652190128234,
            "unit": "iter/sec",
            "range": "stddev: 0.000020313691940949003",
            "extra": "mean: 3.3558564784056992 msec\nrounds: 301"
          },
          {
            "name": "tests/test_benchmarks.py::TestConversationSerdeBenchmark::test_conversation_serde_50msg",
            "value": 633.6408652359548,
            "unit": "iter/sec",
            "range": "stddev: 0.00001622446101654172",
            "extra": "mean: 1.5781810404977912 msec\nrounds: 642"
          },
          {
            "name": "tests/test_benchmarks.py::TestDetectModeBenchmark::test_detect_mode_1000",
            "value": 207.49707812688274,
            "unit": "iter/sec",
            "range": "stddev: 0.00005916184794292324",
            "extra": "mean: 4.819344971154284 msec\nrounds: 208"
          },
          {
            "name": "tests/test_benchmarks.py::TestEntitySearchBenchmark::test_entity_search_200",
            "value": 1936.0765428993907,
            "unit": "iter/sec",
            "range": "stddev: 0.000010996231394403468",
            "extra": "mean: 516.5085046185416 usec\nrounds: 2057"
          },
          {
            "name": "tests/test_benchmarks.py::TestLocalSearchBenchmark::test_local_search_500",
            "value": 3470.8065775813216,
            "unit": "iter/sec",
            "range": "stddev: 0.00001012341517086898",
            "extra": "mean: 288.1174671211046 usec\nrounds: 3665"
          },
          {
            "name": "tests/test_benchmarks.py::TestWorkflowParseBenchmark::test_parse_20_step_workflow",
            "value": 16897.289061883577,
            "unit": "iter/sec",
            "range": "stddev: 0.0000036730146577811447",
            "extra": "mean: 59.18109090385224 usec\nrounds: 17326"
          },
          {
            "name": "tests/test_benchmarks.py::TestYAMLLoadBenchmark::test_load_yaml_10_steps",
            "value": 328.3016076697486,
            "unit": "iter/sec",
            "range": "stddev: 0.000060497258501809056",
            "extra": "mean: 3.045979601190193 msec\nrounds: 336"
          },
          {
            "name": "tests/test_benchmarks.py::TestConditionEvalBenchmark::test_condition_evaluate_1000",
            "value": 4826.587052408456,
            "unit": "iter/sec",
            "range": "stddev: 0.000013355238165848425",
            "extra": "mean: 207.1857379016923 usec\nrounds: 5166"
          },
          {
            "name": "tests/test_benchmarks.py::TestCacheBenchmark::test_cache_set_get_1000",
            "value": 35.665406734325984,
            "unit": "iter/sec",
            "range": "stddev: 0.00011882176906048314",
            "extra": "mean: 28.038373638889563 msec\nrounds: 36"
          },
          {
            "name": "tests/test_benchmarks.py::TestTaskStoreBenchmark::test_record_query_100",
            "value": 9.783616838877494,
            "unit": "iter/sec",
            "range": "stddev: 0.007902420261350194",
            "extra": "mean: 102.21168883334286 msec\nrounds: 12"
          },
          {
            "name": "tests/test_benchmarks.py::TestBudgetBenchmark::test_budget_record_usage_500",
            "value": 548.0001422255922,
            "unit": "iter/sec",
            "range": "stddev: 0.000027220193211886818",
            "extra": "mean: 1.8248170446429108 msec\nrounds: 560"
          },
          {
            "name": "tests/test_benchmarks.py::TestCheckpointBenchmark::test_checkpoint_lifecycle_20",
            "value": 46.39916542483742,
            "unit": "iter/sec",
            "range": "stddev: 0.0033274973727662207",
            "extra": "mean: 21.55211178571546 msec\nrounds: 56"
          },
          {
            "name": "tests/test_benchmarks.py::TestSkillLookupBenchmark::test_skill_lookup_100",
            "value": 9144.967231450806,
            "unit": "iter/sec",
            "range": "stddev: 0.0000036349496301643803",
            "extra": "mean: 109.3497630654008 usec\nrounds: 9395"
          },
          {
            "name": "tests/test_benchmarks.py::TestSessionControllerBenchmark::test_policy_check_latency",
            "value": 1323293.5925939362,
            "unit": "iter/sec",
            "range": "stddev: 9.964389136640786e-8",
            "extra": "mean: 755.6902002674915 nsec\nrounds: 139218"
          },
          {
            "name": "tests/test_benchmarks.py::TestSessionControllerBenchmark::test_event_log_throughput",
            "value": 6024.028612005759,
            "unit": "iter/sec",
            "range": "stddev: 0.000007934826631735153",
            "extra": "mean: 166.00186758858044 usec\nrounds: 6291"
          },
          {
            "name": "tests/test_benchmarks.py::TestCheckpointBenchmark::test_checkpoint_save_latency",
            "value": 1038.734684158803,
            "unit": "iter/sec",
            "range": "stddev: 0.00045501567289188806",
            "extra": "mean: 962.7097421993071 usec\nrounds: 1346"
          },
          {
            "name": "tests/test_benchmarks.py::TestCheckpointBenchmark::test_checkpoint_load_latency",
            "value": 5744.855125013121,
            "unit": "iter/sec",
            "range": "stddev: 0.000011594999141283841",
            "extra": "mean: 174.06879342283082 usec\nrounds: 6264"
          },
          {
            "name": "tests/test_benchmarks.py::TestCheckpointBenchmark::test_checkpoint_list_recent",
            "value": 4977.874131643167,
            "unit": "iter/sec",
            "range": "stddev: 0.000027460687333546596",
            "extra": "mean: 200.88896857460435 usec\nrounds: 5346"
          },
          {
            "name": "tests/test_benchmarks.py::TestContextManagerBenchmark::test_finalize_summary_latency",
            "value": 247037.26728953668,
            "unit": "iter/sec",
            "range": "stddev: 4.760976276646254e-7",
            "extra": "mean: 4.04797223905478 usec\nrounds: 128634"
          },
          {
            "name": "tests/test_benchmarks.py::TestResolverBenchmark::test_resolve_50_intents",
            "value": 679.7847903422422,
            "unit": "iter/sec",
            "range": "stddev: 0.000017928720101786717",
            "extra": "mean: 1.4710538014487544 msec\nrounds: 690"
          },
          {
            "name": "tests/test_benchmarks.py::TestStructuralOverlapBenchmark::test_structural_overlaps_1000",
            "value": 281.53435868622563,
            "unit": "iter/sec",
            "range": "stddev: 0.00013828167496592563",
            "extra": "mean: 3.5519643309842523 msec\nrounds: 284"
          },
          {
            "name": "tests/test_benchmarks.py::TestConstraintBenchmark::test_validate_20_constraints",
            "value": 193065.80987621643,
            "unit": "iter/sec",
            "range": "stddev: 0.0000013428728266821059",
            "extra": "mean: 5.179580996972726 usec\nrounds: 100726"
          },
          {
            "name": "tests/test_benchmarks.py::TestPhiScoringBenchmark::test_phi_score_100_outcomes",
            "value": 83995.30188263541,
            "unit": "iter/sec",
            "range": "stddev: 0.0000011769827789460408",
            "extra": "mean: 11.905427774963838 usec\nrounds: 87712"
          },
          {
            "name": "tests/test_benchmarks.py::TestRealisticScenarioBenchmark::test_realistic_25_agents",
            "value": 198.9587041878196,
            "unit": "iter/sec",
            "range": "stddev: 0.00003551177447536673",
            "extra": "mean: 5.026168641790043 msec\nrounds: 201"
          },
          {
            "name": "tests/test_benchmarks.py::TestPublishThroughputBenchmark::test_publish_100_intents",
            "value": 834.2829688097818,
            "unit": "iter/sec",
            "range": "stddev: 0.00002397015143519046",
            "extra": "mean: 1.1986340814635545 msec\nrounds: 847"
          }
        ]
      }
    ]
  }
}