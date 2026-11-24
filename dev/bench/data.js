window.BENCHMARK_DATA = {
  "lastUpdate": 1795484954105,
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
          "id": "5a5a9dd2c5cbb386808b8b2bef0b4d7a5395bcea",
          "message": "fix(release): align Core package matrix metadata (#144)",
          "timestamp": "2026-10-18T16:20:04-07:00",
          "tree_id": "1610eda481b4168a41a38d2525aa7bf044825a53",
          "url": "https://github.com/Arete-Consortium/animus/commit/5a5a9dd2c5cbb386808b8b2bef0b4d7a5395bcea"
        },
        "date": 1792366721454,
        "tool": "pytest",
        "benches": [
          {
            "name": "tests/test_benchmarks.py::TestMemorySerdeBenchmark::test_memory_serde_500",
            "value": 309.34304353813974,
            "unit": "iter/sec",
            "range": "stddev: 0.00005177726942446517",
            "extra": "mean: 3.2326571451628823 msec\nrounds: 310"
          },
          {
            "name": "tests/test_benchmarks.py::TestConversationSerdeBenchmark::test_conversation_serde_50msg",
            "value": 651.9843669970807,
            "unit": "iter/sec",
            "range": "stddev: 0.000023302648121957587",
            "extra": "mean: 1.533779106707443 msec\nrounds: 656"
          },
          {
            "name": "tests/test_benchmarks.py::TestDetectModeBenchmark::test_detect_mode_1000",
            "value": 200.1294048562599,
            "unit": "iter/sec",
            "range": "stddev: 0.00006617810316220803",
            "extra": "mean: 4.996766970442129 msec\nrounds: 203"
          },
          {
            "name": "tests/test_benchmarks.py::TestEntitySearchBenchmark::test_entity_search_200",
            "value": 1995.350173191564,
            "unit": "iter/sec",
            "range": "stddev: 0.000014314614243825561",
            "extra": "mean: 501.1651656112567 usec\nrounds: 2053"
          },
          {
            "name": "tests/test_benchmarks.py::TestLocalSearchBenchmark::test_local_search_500",
            "value": 3485.92004008805,
            "unit": "iter/sec",
            "range": "stddev: 0.000013276175553740254",
            "extra": "mean: 286.8683126692548 usec\nrounds: 3694"
          },
          {
            "name": "tests/test_benchmarks.py::TestWorkflowParseBenchmark::test_parse_20_step_workflow",
            "value": 16424.09946785215,
            "unit": "iter/sec",
            "range": "stddev: 0.000011383489485674733",
            "extra": "mean: 60.88613880824081 usec\nrounds: 17254"
          },
          {
            "name": "tests/test_benchmarks.py::TestYAMLLoadBenchmark::test_load_yaml_10_steps",
            "value": 334.0688340167221,
            "unit": "iter/sec",
            "range": "stddev: 0.00003419028255467943",
            "extra": "mean: 2.9933950676462806 msec\nrounds: 340"
          },
          {
            "name": "tests/test_benchmarks.py::TestConditionEvalBenchmark::test_condition_evaluate_1000",
            "value": 4749.387063202642,
            "unit": "iter/sec",
            "range": "stddev: 0.000011574841539321914",
            "extra": "mean: 210.553485469275 usec\nrounds: 4783"
          },
          {
            "name": "tests/test_benchmarks.py::TestCacheBenchmark::test_cache_set_get_1000",
            "value": 35.32273935108411,
            "unit": "iter/sec",
            "range": "stddev: 0.000196645072407314",
            "extra": "mean: 28.310375083333067 msec\nrounds: 36"
          },
          {
            "name": "tests/test_benchmarks.py::TestTaskStoreBenchmark::test_record_query_100",
            "value": 11.624980691997068,
            "unit": "iter/sec",
            "range": "stddev: 0.0045483005416400765",
            "extra": "mean: 86.02164824999885 msec\nrounds: 12"
          },
          {
            "name": "tests/test_benchmarks.py::TestBudgetBenchmark::test_budget_record_usage_500",
            "value": 539.8889989775886,
            "unit": "iter/sec",
            "range": "stddev: 0.00002560791887775834",
            "extra": "mean: 1.8522325920582634 msec\nrounds: 554"
          },
          {
            "name": "tests/test_benchmarks.py::TestCheckpointBenchmark::test_checkpoint_lifecycle_20",
            "value": 49.36315268035341,
            "unit": "iter/sec",
            "range": "stddev: 0.0017751094345748156",
            "extra": "mean: 20.25802538333418 msec\nrounds: 60"
          },
          {
            "name": "tests/test_benchmarks.py::TestSkillLookupBenchmark::test_skill_lookup_100",
            "value": 9555.875649452277,
            "unit": "iter/sec",
            "range": "stddev: 0.000003724464243725892",
            "extra": "mean: 104.64765728270208 usec\nrounds: 9804"
          },
          {
            "name": "tests/test_benchmarks.py::TestSessionControllerBenchmark::test_policy_check_latency",
            "value": 1316935.1008486552,
            "unit": "iter/sec",
            "range": "stddev: 9.476761187452533e-8",
            "extra": "mean: 759.3388613877654 nsec\nrounds: 136148"
          },
          {
            "name": "tests/test_benchmarks.py::TestSessionControllerBenchmark::test_event_log_throughput",
            "value": 6004.458504216917,
            "unit": "iter/sec",
            "range": "stddev: 0.000012664501288016789",
            "extra": "mean: 166.54291128795415 usec\nrounds: 6290"
          },
          {
            "name": "tests/test_benchmarks.py::TestCheckpointBenchmark::test_checkpoint_save_latency",
            "value": 1129.3943836321744,
            "unit": "iter/sec",
            "range": "stddev: 0.00037065791023188117",
            "extra": "mean: 885.4302929893831 usec\nrounds: 1355"
          },
          {
            "name": "tests/test_benchmarks.py::TestCheckpointBenchmark::test_checkpoint_load_latency",
            "value": 5645.3458338781675,
            "unit": "iter/sec",
            "range": "stddev: 0.000013440762550393052",
            "extra": "mean: 177.13706643070842 usec\nrounds: 6217"
          },
          {
            "name": "tests/test_benchmarks.py::TestCheckpointBenchmark::test_checkpoint_list_recent",
            "value": 4932.882883396858,
            "unit": "iter/sec",
            "range": "stddev: 0.0000167853328183132",
            "extra": "mean: 202.7212126535193 usec\nrounds: 5295"
          },
          {
            "name": "tests/test_benchmarks.py::TestContextManagerBenchmark::test_finalize_summary_latency",
            "value": 248392.40310088533,
            "unit": "iter/sec",
            "range": "stddev: 5.400066908258123e-7",
            "extra": "mean: 4.025888020391054 usec\nrounds: 126840"
          },
          {
            "name": "tests/test_benchmarks.py::TestResolverBenchmark::test_resolve_50_intents",
            "value": 677.3897304142687,
            "unit": "iter/sec",
            "range": "stddev: 0.00001983718023917735",
            "extra": "mean: 1.4762550347322712 msec\nrounds: 691"
          },
          {
            "name": "tests/test_benchmarks.py::TestStructuralOverlapBenchmark::test_structural_overlaps_1000",
            "value": 287.68427370175345,
            "unit": "iter/sec",
            "range": "stddev: 0.00011283657546113903",
            "extra": "mean: 3.476032899305142 msec\nrounds: 288"
          },
          {
            "name": "tests/test_benchmarks.py::TestConstraintBenchmark::test_validate_20_constraints",
            "value": 201649.75172684318,
            "unit": "iter/sec",
            "range": "stddev: 8.194184465586759e-7",
            "extra": "mean: 4.959093633572187 usec\nrounds: 102271"
          },
          {
            "name": "tests/test_benchmarks.py::TestPhiScoringBenchmark::test_phi_score_100_outcomes",
            "value": 86092.93228988702,
            "unit": "iter/sec",
            "range": "stddev: 0.0000011972450683714902",
            "extra": "mean: 11.615355330596238 usec\nrounds: 90572"
          },
          {
            "name": "tests/test_benchmarks.py::TestRealisticScenarioBenchmark::test_realistic_25_agents",
            "value": 197.03633782363912,
            "unit": "iter/sec",
            "range": "stddev: 0.00007415021768007895",
            "extra": "mean: 5.075205980000845 msec\nrounds: 200"
          },
          {
            "name": "tests/test_benchmarks.py::TestPublishThroughputBenchmark::test_publish_100_intents",
            "value": 823.6727676700608,
            "unit": "iter/sec",
            "range": "stddev: 0.000021103874812951",
            "extra": "mean: 1.2140743742551054 msec\nrounds: 839"
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
          "id": "5fbbc1c5c667ac439f1151fcd7d5953dfab4ff2e",
          "message": "feat(pwa): add read-only tools dashboard shell\n\nAdmin-approved merge after all CI checks passed. Review requirement bypassed by explicit maintainer authorization.",
          "timestamp": "2026-11-15T23:22:56-08:00",
          "tree_id": "e04e73f3dfdb91e7921dff662cc63a92fd725c2c",
          "url": "https://github.com/Arete-Consortium/animus/commit/5fbbc1c5c667ac439f1151fcd7d5953dfab4ff2e"
        },
        "date": 1794814915200,
        "tool": "pytest",
        "benches": [
          {
            "name": "tests/test_benchmarks.py::TestMemorySerdeBenchmark::test_memory_serde_500",
            "value": 475.66764715852526,
            "unit": "iter/sec",
            "range": "stddev: 0.0000401622931182466",
            "extra": "mean: 2.102308210309563 msec\nrounds: 485"
          },
          {
            "name": "tests/test_benchmarks.py::TestConversationSerdeBenchmark::test_conversation_serde_50msg",
            "value": 1076.186335771113,
            "unit": "iter/sec",
            "range": "stddev: 0.00001355328815578085",
            "extra": "mean: 929.2071147544133 usec\nrounds: 1098"
          },
          {
            "name": "tests/test_benchmarks.py::TestDetectModeBenchmark::test_detect_mode_1000",
            "value": 366.42153570982794,
            "unit": "iter/sec",
            "range": "stddev: 0.000025984498511033313",
            "extra": "mean: 2.729097235136059 msec\nrounds: 370"
          },
          {
            "name": "tests/test_benchmarks.py::TestEntitySearchBenchmark::test_entity_search_200",
            "value": 3072.1007161294788,
            "unit": "iter/sec",
            "range": "stddev: 0.00003588186929555325",
            "extra": "mean: 325.5101614181106 usec\nrounds: 3271"
          },
          {
            "name": "tests/test_benchmarks.py::TestLocalSearchBenchmark::test_local_search_500",
            "value": 5694.511116143559,
            "unit": "iter/sec",
            "range": "stddev: 0.0000053573861554395995",
            "extra": "mean: 175.60770004734326 usec\nrounds: 6321"
          },
          {
            "name": "tests/test_benchmarks.py::TestWorkflowParseBenchmark::test_parse_20_step_workflow",
            "value": 27645.041159571083,
            "unit": "iter/sec",
            "range": "stddev: 0.0000022449527373130164",
            "extra": "mean: 36.172852636675735 usec\nrounds: 28881"
          },
          {
            "name": "tests/test_benchmarks.py::TestYAMLLoadBenchmark::test_load_yaml_10_steps",
            "value": 582.6346588428016,
            "unit": "iter/sec",
            "range": "stddev: 0.00014987589833697593",
            "extra": "mean: 1.7163414239484953 msec\nrounds: 618"
          },
          {
            "name": "tests/test_benchmarks.py::TestConditionEvalBenchmark::test_condition_evaluate_1000",
            "value": 8404.775280620746,
            "unit": "iter/sec",
            "range": "stddev: 0.0000042427230421052544",
            "extra": "mean: 118.97998061955842 usec\nrounds: 8875"
          },
          {
            "name": "tests/test_benchmarks.py::TestCacheBenchmark::test_cache_set_get_1000",
            "value": 65.30257599814337,
            "unit": "iter/sec",
            "range": "stddev: 0.00005341467516848666",
            "extra": "mean: 15.313331590907396 msec\nrounds: 66"
          },
          {
            "name": "tests/test_benchmarks.py::TestTaskStoreBenchmark::test_record_query_100",
            "value": 28.049367876203963,
            "unit": "iter/sec",
            "range": "stddev: 0.0016744619467679322",
            "extra": "mean: 35.65142731249793 msec\nrounds: 32"
          },
          {
            "name": "tests/test_benchmarks.py::TestBudgetBenchmark::test_budget_record_usage_500",
            "value": 936.2275411396942,
            "unit": "iter/sec",
            "range": "stddev: 0.000046350196102519865",
            "extra": "mean: 1.0681164098021234 msec\nrounds: 959"
          },
          {
            "name": "tests/test_benchmarks.py::TestCheckpointBenchmark::test_checkpoint_lifecycle_20",
            "value": 128.46898431031994,
            "unit": "iter/sec",
            "range": "stddev: 0.0007010535026873675",
            "extra": "mean: 7.7839799650355745 msec\nrounds: 143"
          },
          {
            "name": "tests/test_benchmarks.py::TestSkillLookupBenchmark::test_skill_lookup_100",
            "value": 15685.858278511134,
            "unit": "iter/sec",
            "range": "stddev: 0.000002951088295393651",
            "extra": "mean: 63.751691634875435 usec\nrounds: 17035"
          },
          {
            "name": "tests/test_benchmarks.py::TestSessionControllerBenchmark::test_policy_check_latency",
            "value": 2265613.454620661,
            "unit": "iter/sec",
            "range": "stddev: 6.674987828469939e-8",
            "extra": "mean: 441.3815595773963 nsec\nrounds: 198571"
          },
          {
            "name": "tests/test_benchmarks.py::TestSessionControllerBenchmark::test_event_log_throughput",
            "value": 9941.939287835903,
            "unit": "iter/sec",
            "range": "stddev: 0.00003822407157456753",
            "extra": "mean: 100.58399785477602 usec\nrounds: 10722"
          },
          {
            "name": "tests/test_benchmarks.py::TestCheckpointBenchmark::test_checkpoint_save_latency",
            "value": 2393.020664269853,
            "unit": "iter/sec",
            "range": "stddev: 0.00006196879592577723",
            "extra": "mean: 417.8818908382119 usec\nrounds: 3078"
          },
          {
            "name": "tests/test_benchmarks.py::TestCheckpointBenchmark::test_checkpoint_load_latency",
            "value": 13688.747727855942,
            "unit": "iter/sec",
            "range": "stddev: 0.0000069202464224363925",
            "extra": "mean: 73.05270137786586 usec\nrounds: 15240"
          },
          {
            "name": "tests/test_benchmarks.py::TestCheckpointBenchmark::test_checkpoint_list_recent",
            "value": 11312.799004694783,
            "unit": "iter/sec",
            "range": "stddev: 0.000006169251366601058",
            "extra": "mean: 88.3954536437006 usec\nrounds: 12199"
          },
          {
            "name": "tests/test_benchmarks.py::TestContextManagerBenchmark::test_finalize_summary_latency",
            "value": 414773.8665824744,
            "unit": "iter/sec",
            "range": "stddev: 2.2160276597730801e-7",
            "extra": "mean: 2.410952281635994 usec\nrounds: 43631"
          },
          {
            "name": "tests/test_benchmarks.py::TestResolverBenchmark::test_resolve_50_intents",
            "value": 1112.7208011741336,
            "unit": "iter/sec",
            "range": "stddev: 0.00001805962272216666",
            "extra": "mean: 898.698037229832 usec\nrounds: 1155"
          },
          {
            "name": "tests/test_benchmarks.py::TestStructuralOverlapBenchmark::test_structural_overlaps_1000",
            "value": 461.33793391936507,
            "unit": "iter/sec",
            "range": "stddev: 0.00003325694414143928",
            "extra": "mean: 2.167608441613182 msec\nrounds: 471"
          },
          {
            "name": "tests/test_benchmarks.py::TestConstraintBenchmark::test_validate_20_constraints",
            "value": 286786.16186800133,
            "unit": "iter/sec",
            "range": "stddev: 4.743851996830881e-7",
            "extra": "mean: 3.486918592886182 usec\nrounds: 152370"
          },
          {
            "name": "tests/test_benchmarks.py::TestPhiScoringBenchmark::test_phi_score_100_outcomes",
            "value": 147473.42545346104,
            "unit": "iter/sec",
            "range": "stddev: 9.805742277778674e-7",
            "extra": "mean: 6.780882704291528 usec\nrounds: 157704"
          },
          {
            "name": "tests/test_benchmarks.py::TestRealisticScenarioBenchmark::test_realistic_25_agents",
            "value": 322.9662290005296,
            "unit": "iter/sec",
            "range": "stddev: 0.000018968918062890346",
            "extra": "mean: 3.096298963190855 msec\nrounds: 326"
          },
          {
            "name": "tests/test_benchmarks.py::TestPublishThroughputBenchmark::test_publish_100_intents",
            "value": 1526.172422266991,
            "unit": "iter/sec",
            "range": "stddev: 0.000009679336950138889",
            "extra": "mean: 655.2339600754879 usec\nrounds: 1578"
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
          "id": "76e237a279e239881b4342db7271a62c631910c0",
          "message": "Add dry-run bootstrap memory importer (#149)\n\n* add dry-run bootstrap memory importer\n\n* style: format memory importer\n\n---------\n\nCo-authored-by: AreteDriver <AreteDriver@users.noreply.github.com>",
          "timestamp": "2026-11-16T02:28:34-08:00",
          "tree_id": "b90be126da936724586119d670c3da2574f4e15d",
          "url": "https://github.com/Arete-Consortium/animus/commit/76e237a279e239881b4342db7271a62c631910c0"
        },
        "date": 1794826025193,
        "tool": "pytest",
        "benches": [
          {
            "name": "tests/test_benchmarks.py::TestMemorySerdeBenchmark::test_memory_serde_500",
            "value": 308.4200769679,
            "unit": "iter/sec",
            "range": "stddev: 0.00011862443649069054",
            "extra": "mean: 3.2423310759502817 msec\nrounds: 316"
          },
          {
            "name": "tests/test_benchmarks.py::TestConversationSerdeBenchmark::test_conversation_serde_50msg",
            "value": 678.6614905425706,
            "unit": "iter/sec",
            "range": "stddev: 0.00005216022837465658",
            "extra": "mean: 1.4734886448331235 msec\nrounds: 687"
          },
          {
            "name": "tests/test_benchmarks.py::TestDetectModeBenchmark::test_detect_mode_1000",
            "value": 228.4603746975926,
            "unit": "iter/sec",
            "range": "stddev: 0.00011656630798975301",
            "extra": "mean: 4.3771266738211185 msec\nrounds: 233"
          },
          {
            "name": "tests/test_benchmarks.py::TestEntitySearchBenchmark::test_entity_search_200",
            "value": 1925.6770797858378,
            "unit": "iter/sec",
            "range": "stddev: 0.000013205522562354412",
            "extra": "mean: 519.2978669669859 usec\nrounds: 1992"
          },
          {
            "name": "tests/test_benchmarks.py::TestLocalSearchBenchmark::test_local_search_500",
            "value": 3471.755321104532,
            "unit": "iter/sec",
            "range": "stddev: 0.0000287254471169318",
            "extra": "mean: 288.0387318544822 usec\nrounds: 3651"
          },
          {
            "name": "tests/test_benchmarks.py::TestWorkflowParseBenchmark::test_parse_20_step_workflow",
            "value": 17399.40613534447,
            "unit": "iter/sec",
            "range": "stddev: 0.000003131324179603828",
            "extra": "mean: 57.47322593778872 usec\nrounds: 17704"
          },
          {
            "name": "tests/test_benchmarks.py::TestYAMLLoadBenchmark::test_load_yaml_10_steps",
            "value": 339.5638132749026,
            "unit": "iter/sec",
            "range": "stddev: 0.00005031194282560155",
            "extra": "mean: 2.944954559072596 msec\nrounds: 347"
          },
          {
            "name": "tests/test_benchmarks.py::TestConditionEvalBenchmark::test_condition_evaluate_1000",
            "value": 5195.531221311527,
            "unit": "iter/sec",
            "range": "stddev: 0.000006450936262859984",
            "extra": "mean: 192.4730999398299 usec\nrounds: 4993"
          },
          {
            "name": "tests/test_benchmarks.py::TestCacheBenchmark::test_cache_set_get_1000",
            "value": 36.16125413858764,
            "unit": "iter/sec",
            "range": "stddev: 0.00018062581739634976",
            "extra": "mean: 27.653908135141286 msec\nrounds: 37"
          },
          {
            "name": "tests/test_benchmarks.py::TestTaskStoreBenchmark::test_record_query_100",
            "value": 11.337160980972365,
            "unit": "iter/sec",
            "range": "stddev: 0.005041902399522604",
            "extra": "mean: 88.20550415384787 msec\nrounds: 13"
          },
          {
            "name": "tests/test_benchmarks.py::TestBudgetBenchmark::test_budget_record_usage_500",
            "value": 541.76385747338,
            "unit": "iter/sec",
            "range": "stddev: 0.00003163530200902061",
            "extra": "mean: 1.8458226517060266 msec\nrounds: 557"
          },
          {
            "name": "tests/test_benchmarks.py::TestCheckpointBenchmark::test_checkpoint_lifecycle_20",
            "value": 51.72211980103427,
            "unit": "iter/sec",
            "range": "stddev: 0.0017367372890217427",
            "extra": "mean: 19.334087694913144 msec\nrounds: 59"
          },
          {
            "name": "tests/test_benchmarks.py::TestSkillLookupBenchmark::test_skill_lookup_100",
            "value": 9360.384211906261,
            "unit": "iter/sec",
            "range": "stddev: 0.000005286742736093515",
            "extra": "mean: 106.83322151755434 usec\nrounds: 9620"
          },
          {
            "name": "tests/test_benchmarks.py::TestSessionControllerBenchmark::test_policy_check_latency",
            "value": 1441750.7500488325,
            "unit": "iter/sec",
            "range": "stddev: 9.225059095682343e-8",
            "extra": "mean: 693.6011650877448 nsec\nrounds: 147886"
          },
          {
            "name": "tests/test_benchmarks.py::TestSessionControllerBenchmark::test_event_log_throughput",
            "value": 5874.362723396839,
            "unit": "iter/sec",
            "range": "stddev: 0.00007073404220765154",
            "extra": "mean: 170.231231383981 usec\nrounds: 6258"
          },
          {
            "name": "tests/test_benchmarks.py::TestCheckpointBenchmark::test_checkpoint_save_latency",
            "value": 1126.137486189698,
            "unit": "iter/sec",
            "range": "stddev: 0.00017881738485685296",
            "extra": "mean: 887.991042180395 usec\nrounds: 1375"
          },
          {
            "name": "tests/test_benchmarks.py::TestCheckpointBenchmark::test_checkpoint_load_latency",
            "value": 5733.15764490238,
            "unit": "iter/sec",
            "range": "stddev: 0.000013315339152487788",
            "extra": "mean: 174.4239495819807 usec\nrounds: 6228"
          },
          {
            "name": "tests/test_benchmarks.py::TestCheckpointBenchmark::test_checkpoint_list_recent",
            "value": 5034.680680335349,
            "unit": "iter/sec",
            "range": "stddev: 0.000012256772561571197",
            "extra": "mean: 198.62232850354118 usec\nrounds: 5315"
          },
          {
            "name": "tests/test_benchmarks.py::TestContextManagerBenchmark::test_finalize_summary_latency",
            "value": 270599.82918768004,
            "unit": "iter/sec",
            "range": "stddev: 4.604305104774836e-7",
            "extra": "mean: 3.6954938330963607 usec\nrounds: 139782"
          },
          {
            "name": "tests/test_benchmarks.py::TestResolverBenchmark::test_resolve_50_intents",
            "value": 705.989729276794,
            "unit": "iter/sec",
            "range": "stddev: 0.00004919858831042277",
            "extra": "mean: 1.4164512011022963 msec\nrounds: 726"
          },
          {
            "name": "tests/test_benchmarks.py::TestStructuralOverlapBenchmark::test_structural_overlaps_1000",
            "value": 287.42151381243525,
            "unit": "iter/sec",
            "range": "stddev: 0.00012181003719211399",
            "extra": "mean: 3.479210678197796 msec\nrounds: 289"
          },
          {
            "name": "tests/test_benchmarks.py::TestConstraintBenchmark::test_validate_20_constraints",
            "value": 185071.47505460307,
            "unit": "iter/sec",
            "range": "stddev: 9.336693184890147e-7",
            "extra": "mean: 5.403317824667266 usec\nrounds: 191571"
          },
          {
            "name": "tests/test_benchmarks.py::TestPhiScoringBenchmark::test_phi_score_100_outcomes",
            "value": 85936.3389420379,
            "unit": "iter/sec",
            "range": "stddev: 0.0000012758902317572025",
            "extra": "mean: 11.63652085149307 usec\nrounds: 91408"
          },
          {
            "name": "tests/test_benchmarks.py::TestRealisticScenarioBenchmark::test_realistic_25_agents",
            "value": 196.80262412520497,
            "unit": "iter/sec",
            "range": "stddev: 0.0000488331492488608",
            "extra": "mean: 5.081233060001296 msec\nrounds: 200"
          },
          {
            "name": "tests/test_benchmarks.py::TestPublishThroughputBenchmark::test_publish_100_intents",
            "value": 896.4949861331758,
            "unit": "iter/sec",
            "range": "stddev: 0.000020233063088051402",
            "extra": "mean: 1.1154552066300663 msec\nrounds: 905"
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
          "id": "b053f66d8d73b58296ee12ba11b843b733b0d77a",
          "message": "Fix Animus Core 2.3 Bootstrap compatibility\n\n* Fix Animus Core 2.3 bootstrap compatibility\n\n* Make Core discovery regression test standalone",
          "timestamp": "2026-11-17T20:53:49-08:00",
          "tree_id": "b83c29ab291ec71b7a40f6f89223d3ebd4ebc45d",
          "url": "https://github.com/Arete-Consortium/animus/commit/b053f66d8d73b58296ee12ba11b843b733b0d77a"
        },
        "date": 1794978738853,
        "tool": "pytest",
        "benches": [
          {
            "name": "tests/test_benchmarks.py::TestMemorySerdeBenchmark::test_memory_serde_500",
            "value": 402.2897973702207,
            "unit": "iter/sec",
            "range": "stddev: 0.00003080052134385909",
            "extra": "mean: 2.4857702246913225 msec\nrounds: 405"
          },
          {
            "name": "tests/test_benchmarks.py::TestConversationSerdeBenchmark::test_conversation_serde_50msg",
            "value": 883.7386643979116,
            "unit": "iter/sec",
            "range": "stddev: 0.00012067712947150102",
            "extra": "mean: 1.1315562397411874 msec\nrounds: 926"
          },
          {
            "name": "tests/test_benchmarks.py::TestDetectModeBenchmark::test_detect_mode_1000",
            "value": 308.28562586699536,
            "unit": "iter/sec",
            "range": "stddev: 0.00015329108556694264",
            "extra": "mean: 3.2437451379307354 msec\nrounds: 319"
          },
          {
            "name": "tests/test_benchmarks.py::TestEntitySearchBenchmark::test_entity_search_200",
            "value": 2485.1415227168586,
            "unit": "iter/sec",
            "range": "stddev: 0.000017169822941220446",
            "extra": "mean: 402.39157040310477 usec\nrounds: 2507"
          },
          {
            "name": "tests/test_benchmarks.py::TestLocalSearchBenchmark::test_local_search_500",
            "value": 4860.725319852973,
            "unit": "iter/sec",
            "range": "stddev: 0.000010287385365369715",
            "extra": "mean: 205.73061306625075 usec\nrounds: 4944"
          },
          {
            "name": "tests/test_benchmarks.py::TestWorkflowParseBenchmark::test_parse_20_step_workflow",
            "value": 22223.567058742072,
            "unit": "iter/sec",
            "range": "stddev: 0.0000029526016763311675",
            "extra": "mean: 44.99727687084466 usec\nrounds: 22971"
          },
          {
            "name": "tests/test_benchmarks.py::TestYAMLLoadBenchmark::test_load_yaml_10_steps",
            "value": 518.90754492105,
            "unit": "iter/sec",
            "range": "stddev: 0.00003130652810511279",
            "extra": "mean: 1.9271255733083368 msec\nrounds: 532"
          },
          {
            "name": "tests/test_benchmarks.py::TestConditionEvalBenchmark::test_condition_evaluate_1000",
            "value": 6103.199269648411,
            "unit": "iter/sec",
            "range": "stddev: 0.000005045881382199831",
            "extra": "mean: 163.8484925394886 usec\nrounds: 6032"
          },
          {
            "name": "tests/test_benchmarks.py::TestCacheBenchmark::test_cache_set_get_1000",
            "value": 48.96748718584224,
            "unit": "iter/sec",
            "range": "stddev: 0.0006003523328980055",
            "extra": "mean: 20.42171361999408 msec\nrounds: 50"
          },
          {
            "name": "tests/test_benchmarks.py::TestTaskStoreBenchmark::test_record_query_100",
            "value": 12.517500585170556,
            "unit": "iter/sec",
            "range": "stddev: 0.006462773939808344",
            "extra": "mean: 79.88815284615978 msec\nrounds: 13"
          },
          {
            "name": "tests/test_benchmarks.py::TestBudgetBenchmark::test_budget_record_usage_500",
            "value": 716.5440168767586,
            "unit": "iter/sec",
            "range": "stddev: 0.00021501463358977887",
            "extra": "mean: 1.3955876770261193 msec\nrounds: 740"
          },
          {
            "name": "tests/test_benchmarks.py::TestCheckpointBenchmark::test_checkpoint_lifecycle_20",
            "value": 33.357718142985185,
            "unit": "iter/sec",
            "range": "stddev: 0.06399858265502087",
            "extra": "mean: 29.978069714288615 msec\nrounds: 63"
          },
          {
            "name": "tests/test_benchmarks.py::TestSkillLookupBenchmark::test_skill_lookup_100",
            "value": 13084.727627761798,
            "unit": "iter/sec",
            "range": "stddev: 0.0000029147335651294422",
            "extra": "mean: 76.42497638837398 usec\nrounds: 13468"
          },
          {
            "name": "tests/test_benchmarks.py::TestSessionControllerBenchmark::test_policy_check_latency",
            "value": 1876441.729270768,
            "unit": "iter/sec",
            "range": "stddev: 1.3659027852963529e-7",
            "extra": "mean: 532.923556538377 nsec\nrounds: 183218"
          },
          {
            "name": "tests/test_benchmarks.py::TestSessionControllerBenchmark::test_event_log_throughput",
            "value": 8023.995269480027,
            "unit": "iter/sec",
            "range": "stddev: 0.000025422307590893055",
            "extra": "mean: 124.6261951080141 usec\nrounds: 8667"
          },
          {
            "name": "tests/test_benchmarks.py::TestCheckpointBenchmark::test_checkpoint_save_latency",
            "value": 1160.769957154605,
            "unit": "iter/sec",
            "range": "stddev: 0.0009857175844469358",
            "extra": "mean: 861.4971414760765 usec\nrounds: 1449"
          },
          {
            "name": "tests/test_benchmarks.py::TestCheckpointBenchmark::test_checkpoint_load_latency",
            "value": 7964.817835049328,
            "unit": "iter/sec",
            "range": "stddev: 0.000010466650072728254",
            "extra": "mean: 125.55214955444198 usec\nrounds: 8980"
          },
          {
            "name": "tests/test_benchmarks.py::TestCheckpointBenchmark::test_checkpoint_list_recent",
            "value": 7003.630832804997,
            "unit": "iter/sec",
            "range": "stddev: 0.000009347374505483605",
            "extra": "mean: 142.7830826427917 usec\nrounds: 7599"
          },
          {
            "name": "tests/test_benchmarks.py::TestContextManagerBenchmark::test_finalize_summary_latency",
            "value": 353050.7572919327,
            "unit": "iter/sec",
            "range": "stddev: 4.08115556113786e-7",
            "extra": "mean: 2.832453915891516 usec\nrounds: 183892"
          },
          {
            "name": "tests/test_benchmarks.py::TestResolverBenchmark::test_resolve_50_intents",
            "value": 940.5953434333566,
            "unit": "iter/sec",
            "range": "stddev: 0.00003857893483604884",
            "extra": "mean: 1.0631564433965883 msec\nrounds: 954"
          },
          {
            "name": "tests/test_benchmarks.py::TestStructuralOverlapBenchmark::test_structural_overlaps_1000",
            "value": 382.328988111421,
            "unit": "iter/sec",
            "range": "stddev: 0.00012028768921074628",
            "extra": "mean: 2.6155484702838514 msec\nrounds: 387"
          },
          {
            "name": "tests/test_benchmarks.py::TestConstraintBenchmark::test_validate_20_constraints",
            "value": 251375.37284543546,
            "unit": "iter/sec",
            "range": "stddev: 5.480376741851653e-7",
            "extra": "mean: 3.978114437705381 usec\nrounds: 131718"
          },
          {
            "name": "tests/test_benchmarks.py::TestPhiScoringBenchmark::test_phi_score_100_outcomes",
            "value": 113274.33377338552,
            "unit": "iter/sec",
            "range": "stddev: 8.830918992308264e-7",
            "extra": "mean: 8.828125195603278 usec\nrounds: 118878"
          },
          {
            "name": "tests/test_benchmarks.py::TestRealisticScenarioBenchmark::test_realistic_25_agents",
            "value": 288.91609801300984,
            "unit": "iter/sec",
            "range": "stddev: 0.00009232663413352886",
            "extra": "mean: 3.461212465755267 msec\nrounds: 292"
          },
          {
            "name": "tests/test_benchmarks.py::TestPublishThroughputBenchmark::test_publish_100_intents",
            "value": 1267.888056794394,
            "unit": "iter/sec",
            "range": "stddev: 0.000029425616852269395",
            "extra": "mean: 788.7131633121488 usec\nrounds: 1292"
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
          "id": "b053f66d8d73b58296ee12ba11b843b733b0d77a",
          "message": "Fix Animus Core 2.3 Bootstrap compatibility\n\n* Fix Animus Core 2.3 bootstrap compatibility\n\n* Make Core discovery regression test standalone",
          "timestamp": "2026-11-17T20:53:49-08:00",
          "tree_id": "b83c29ab291ec71b7a40f6f89223d3ebd4ebc45d",
          "url": "https://github.com/Arete-Consortium/animus/commit/b053f66d8d73b58296ee12ba11b843b733b0d77a"
        },
        "date": 1794979766714,
        "tool": "pytest",
        "benches": [
          {
            "name": "tests/test_benchmarks.py::TestMemorySerdeBenchmark::test_memory_serde_500",
            "value": 307.6984922027318,
            "unit": "iter/sec",
            "range": "stddev: 0.000045779765810101466",
            "extra": "mean: 3.2499346774216065 msec\nrounds: 310"
          },
          {
            "name": "tests/test_benchmarks.py::TestConversationSerdeBenchmark::test_conversation_serde_50msg",
            "value": 660.2830663578392,
            "unit": "iter/sec",
            "range": "stddev: 0.00006026675697055125",
            "extra": "mean: 1.5145019627961378 msec\nrounds: 672"
          },
          {
            "name": "tests/test_benchmarks.py::TestDetectModeBenchmark::test_detect_mode_1000",
            "value": 220.0496653710101,
            "unit": "iter/sec",
            "range": "stddev: 0.00005210243852470847",
            "extra": "mean: 4.544428633026872 msec\nrounds: 218"
          },
          {
            "name": "tests/test_benchmarks.py::TestEntitySearchBenchmark::test_entity_search_200",
            "value": 1964.389740487243,
            "unit": "iter/sec",
            "range": "stddev: 0.000013411709299325159",
            "extra": "mean: 509.06394967831693 usec\nrounds: 2027"
          },
          {
            "name": "tests/test_benchmarks.py::TestLocalSearchBenchmark::test_local_search_500",
            "value": 3559.0801019380906,
            "unit": "iter/sec",
            "range": "stddev: 0.000019920352618688764",
            "extra": "mean: 280.9714789659979 usec\nrounds: 3708"
          },
          {
            "name": "tests/test_benchmarks.py::TestWorkflowParseBenchmark::test_parse_20_step_workflow",
            "value": 16717.35661282733,
            "unit": "iter/sec",
            "range": "stddev: 0.000003661900394041483",
            "extra": "mean: 59.818069516606094 usec\nrounds: 17305"
          },
          {
            "name": "tests/test_benchmarks.py::TestYAMLLoadBenchmark::test_load_yaml_10_steps",
            "value": 336.49739591360935,
            "unit": "iter/sec",
            "range": "stddev: 0.0001147648396719819",
            "extra": "mean: 2.9717912000030307 msec\nrounds: 345"
          },
          {
            "name": "tests/test_benchmarks.py::TestConditionEvalBenchmark::test_condition_evaluate_1000",
            "value": 4891.712902896302,
            "unit": "iter/sec",
            "range": "stddev: 0.000013493285658979531",
            "extra": "mean: 204.42736927752173 usec\nrounds: 5045"
          },
          {
            "name": "tests/test_benchmarks.py::TestCacheBenchmark::test_cache_set_get_1000",
            "value": 34.545245476939414,
            "unit": "iter/sec",
            "range": "stddev: 0.0022901857599655936",
            "extra": "mean: 28.94754361110409 msec\nrounds: 36"
          },
          {
            "name": "tests/test_benchmarks.py::TestTaskStoreBenchmark::test_record_query_100",
            "value": 10.820588440751795,
            "unit": "iter/sec",
            "range": "stddev: 0.0054273875915257595",
            "extra": "mean: 92.416415749985 msec\nrounds: 12"
          },
          {
            "name": "tests/test_benchmarks.py::TestBudgetBenchmark::test_budget_record_usage_500",
            "value": 531.7120619877778,
            "unit": "iter/sec",
            "range": "stddev: 0.00019527629516999395",
            "extra": "mean: 1.8807171615809357 msec\nrounds: 557"
          },
          {
            "name": "tests/test_benchmarks.py::TestCheckpointBenchmark::test_checkpoint_lifecycle_20",
            "value": 50.1626963921501,
            "unit": "iter/sec",
            "range": "stddev: 0.0021128901038287287",
            "extra": "mean: 19.93513251724819 msec\nrounds: 58"
          },
          {
            "name": "tests/test_benchmarks.py::TestSkillLookupBenchmark::test_skill_lookup_100",
            "value": 9101.261842919212,
            "unit": "iter/sec",
            "range": "stddev: 0.000010677095808533627",
            "extra": "mean: 109.87487419428558 usec\nrounds: 9610"
          },
          {
            "name": "tests/test_benchmarks.py::TestSessionControllerBenchmark::test_policy_check_latency",
            "value": 1376691.868756076,
            "unit": "iter/sec",
            "range": "stddev: 1.1055353363148147e-7",
            "extra": "mean: 726.3789542852172 nsec\nrounds: 142390"
          },
          {
            "name": "tests/test_benchmarks.py::TestSessionControllerBenchmark::test_event_log_throughput",
            "value": 6005.35939036226,
            "unit": "iter/sec",
            "range": "stddev: 0.0000272533915815455",
            "extra": "mean: 166.51792757063907 usec\nrounds: 6420"
          },
          {
            "name": "tests/test_benchmarks.py::TestCheckpointBenchmark::test_checkpoint_save_latency",
            "value": 1108.8974247758883,
            "unit": "iter/sec",
            "range": "stddev: 0.00030005394188460595",
            "extra": "mean: 901.7966654599303 usec\nrounds: 1381"
          },
          {
            "name": "tests/test_benchmarks.py::TestCheckpointBenchmark::test_checkpoint_load_latency",
            "value": 5788.252501122237,
            "unit": "iter/sec",
            "range": "stddev: 0.00001194319700173924",
            "extra": "mean: 172.76371405810616 usec\nrounds: 6274"
          },
          {
            "name": "tests/test_benchmarks.py::TestCheckpointBenchmark::test_checkpoint_list_recent",
            "value": 5095.900731276348,
            "unit": "iter/sec",
            "range": "stddev: 0.000012819658230206705",
            "extra": "mean: 196.2361617176821 usec\nrounds: 5423"
          },
          {
            "name": "tests/test_benchmarks.py::TestContextManagerBenchmark::test_finalize_summary_latency",
            "value": 265326.05093468196,
            "unit": "iter/sec",
            "range": "stddev: 4.5967483792316936e-7",
            "extra": "mean: 3.7689476644951845 usec\nrounds: 136743"
          },
          {
            "name": "tests/test_benchmarks.py::TestResolverBenchmark::test_resolve_50_intents",
            "value": 705.4837463953634,
            "unit": "iter/sec",
            "range": "stddev: 0.00003010070527361684",
            "extra": "mean: 1.4174670998580108 msec\nrounds: 721"
          },
          {
            "name": "tests/test_benchmarks.py::TestStructuralOverlapBenchmark::test_structural_overlaps_1000",
            "value": 290.6170722160579,
            "unit": "iter/sec",
            "range": "stddev: 0.0001287926457775673",
            "extra": "mean: 3.44095407876298 msec\nrounds: 292"
          },
          {
            "name": "tests/test_benchmarks.py::TestConstraintBenchmark::test_validate_20_constraints",
            "value": 181498.44751184835,
            "unit": "iter/sec",
            "range": "stddev: 7.696697814680231e-7",
            "extra": "mean: 5.509689001250103 usec\nrounds: 190840"
          },
          {
            "name": "tests/test_benchmarks.py::TestPhiScoringBenchmark::test_phi_score_100_outcomes",
            "value": 88666.26779283321,
            "unit": "iter/sec",
            "range": "stddev: 0.0000010501008338900915",
            "extra": "mean: 11.27824622478165 usec\nrounds: 93110"
          },
          {
            "name": "tests/test_benchmarks.py::TestRealisticScenarioBenchmark::test_realistic_25_agents",
            "value": 198.179861529106,
            "unit": "iter/sec",
            "range": "stddev: 0.00005071474602090056",
            "extra": "mean: 5.045921378106995 msec\nrounds: 201"
          },
          {
            "name": "tests/test_benchmarks.py::TestPublishThroughputBenchmark::test_publish_100_intents",
            "value": 901.1913553323154,
            "unit": "iter/sec",
            "range": "stddev: 0.000021248693446879028",
            "extra": "mean: 1.109642246436384 msec\nrounds: 913"
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
          "id": "78228daf401683032f6402405a4a33adc3e8e3d8",
          "message": "Make benchmark alerts non-blocking (#152)\n\n* Make benchmark alerts non-blocking\n\n* Make benchmark alert policy informational\n\n* Refresh truth baseline for benchmark alert policy",
          "timestamp": "2026-11-17T21:55:43-08:00",
          "tree_id": "3f073dcd2463cf06ce57e818b3c27f412fd2ab00",
          "url": "https://github.com/Arete-Consortium/animus/commit/78228daf401683032f6402405a4a33adc3e8e3d8"
        },
        "date": 1794982407539,
        "tool": "pytest",
        "benches": [
          {
            "name": "tests/test_benchmarks.py::TestMemorySerdeBenchmark::test_memory_serde_500",
            "value": 296.4657934549117,
            "unit": "iter/sec",
            "range": "stddev: 0.00004096354173816671",
            "extra": "mean: 3.3730704252465 msec\nrounds: 301"
          },
          {
            "name": "tests/test_benchmarks.py::TestConversationSerdeBenchmark::test_conversation_serde_50msg",
            "value": 662.4258408223196,
            "unit": "iter/sec",
            "range": "stddev: 0.000028461097911022193",
            "extra": "mean: 1.5096029447743522 msec\nrounds: 670"
          },
          {
            "name": "tests/test_benchmarks.py::TestDetectModeBenchmark::test_detect_mode_1000",
            "value": 222.3515069381759,
            "unit": "iter/sec",
            "range": "stddev: 0.000023263682283166377",
            "extra": "mean: 4.49738350672859 msec\nrounds: 223"
          },
          {
            "name": "tests/test_benchmarks.py::TestEntitySearchBenchmark::test_entity_search_200",
            "value": 1957.7550365467578,
            "unit": "iter/sec",
            "range": "stddev: 0.000010219665346878773",
            "extra": "mean: 510.78913415228834 usec\nrounds: 2035"
          },
          {
            "name": "tests/test_benchmarks.py::TestLocalSearchBenchmark::test_local_search_500",
            "value": 3666.6526725107,
            "unit": "iter/sec",
            "range": "stddev: 0.0000059871439086459866",
            "extra": "mean: 272.72831361887927 usec\nrounds: 3686"
          },
          {
            "name": "tests/test_benchmarks.py::TestWorkflowParseBenchmark::test_parse_20_step_workflow",
            "value": 16829.248771306036,
            "unit": "iter/sec",
            "range": "stddev: 0.0000028584706823459088",
            "extra": "mean: 59.42035878066083 usec\nrounds: 17356"
          },
          {
            "name": "tests/test_benchmarks.py::TestYAMLLoadBenchmark::test_load_yaml_10_steps",
            "value": 341.5666683132707,
            "unit": "iter/sec",
            "range": "stddev: 0.00008382280704982459",
            "extra": "mean: 2.927686137930887 msec\nrounds: 348"
          },
          {
            "name": "tests/test_benchmarks.py::TestConditionEvalBenchmark::test_condition_evaluate_1000",
            "value": 4864.9841199443235,
            "unit": "iter/sec",
            "range": "stddev: 0.0000049534724237131294",
            "extra": "mean: 205.55051678389538 usec\nrounds: 4975"
          },
          {
            "name": "tests/test_benchmarks.py::TestCacheBenchmark::test_cache_set_get_1000",
            "value": 35.58675971354137,
            "unit": "iter/sec",
            "range": "stddev: 0.00032737180377392586",
            "extra": "mean: 28.100338666672226 msec\nrounds: 36"
          },
          {
            "name": "tests/test_benchmarks.py::TestTaskStoreBenchmark::test_record_query_100",
            "value": 12.260953151867216,
            "unit": "iter/sec",
            "range": "stddev: 0.00497482477927587",
            "extra": "mean: 81.55972766666271 msec\nrounds: 12"
          },
          {
            "name": "tests/test_benchmarks.py::TestBudgetBenchmark::test_budget_record_usage_500",
            "value": 544.0457565803162,
            "unit": "iter/sec",
            "range": "stddev: 0.0001174187548513687",
            "extra": "mean: 1.838080690649358 msec\nrounds: 556"
          },
          {
            "name": "tests/test_benchmarks.py::TestCheckpointBenchmark::test_checkpoint_lifecycle_20",
            "value": 52.22942443586883,
            "unit": "iter/sec",
            "range": "stddev: 0.0015621185752059679",
            "extra": "mean: 19.146295614034084 msec\nrounds: 57"
          },
          {
            "name": "tests/test_benchmarks.py::TestSkillLookupBenchmark::test_skill_lookup_100",
            "value": 9328.58542187066,
            "unit": "iter/sec",
            "range": "stddev: 0.0000035762749862412787",
            "extra": "mean: 107.19738896912733 usec\nrounds: 9700"
          },
          {
            "name": "tests/test_benchmarks.py::TestSessionControllerBenchmark::test_policy_check_latency",
            "value": 1419045.6222238848,
            "unit": "iter/sec",
            "range": "stddev: 8.576118568680187e-8",
            "extra": "mean: 704.69897819975 nsec\nrounds: 146994"
          },
          {
            "name": "tests/test_benchmarks.py::TestSessionControllerBenchmark::test_event_log_throughput",
            "value": 5873.910955959041,
            "unit": "iter/sec",
            "range": "stddev: 0.00005519650348087113",
            "extra": "mean: 170.24432401133134 usec\nrounds: 6222"
          },
          {
            "name": "tests/test_benchmarks.py::TestCheckpointBenchmark::test_checkpoint_save_latency",
            "value": 1165.951788589071,
            "unit": "iter/sec",
            "range": "stddev: 0.00020970566291999364",
            "extra": "mean: 857.6683957148086 usec\nrounds: 1400"
          },
          {
            "name": "tests/test_benchmarks.py::TestCheckpointBenchmark::test_checkpoint_load_latency",
            "value": 5824.471371340533,
            "unit": "iter/sec",
            "range": "stddev: 0.000011744999305135987",
            "extra": "mean: 171.68940084769355 usec\nrounds: 6364"
          },
          {
            "name": "tests/test_benchmarks.py::TestCheckpointBenchmark::test_checkpoint_list_recent",
            "value": 5155.662809097235,
            "unit": "iter/sec",
            "range": "stddev: 0.000011405254781627789",
            "extra": "mean: 193.96148216587918 usec\nrounds: 5467"
          },
          {
            "name": "tests/test_benchmarks.py::TestContextManagerBenchmark::test_finalize_summary_latency",
            "value": 268584.6819819786,
            "unit": "iter/sec",
            "range": "stddev: 4.4193282859576933e-7",
            "extra": "mean: 3.723220522557938 usec\nrounds: 138428"
          },
          {
            "name": "tests/test_benchmarks.py::TestResolverBenchmark::test_resolve_50_intents",
            "value": 716.9089428293609,
            "unit": "iter/sec",
            "range": "stddev: 0.00005405071605699436",
            "extra": "mean: 1.394877285326347 msec\nrounds: 736"
          },
          {
            "name": "tests/test_benchmarks.py::TestStructuralOverlapBenchmark::test_structural_overlaps_1000",
            "value": 295.2891908022973,
            "unit": "iter/sec",
            "range": "stddev: 0.00014395669386259104",
            "extra": "mean: 3.3865106856197875 msec\nrounds: 299"
          },
          {
            "name": "tests/test_benchmarks.py::TestConstraintBenchmark::test_validate_20_constraints",
            "value": 185010.8520525781,
            "unit": "iter/sec",
            "range": "stddev: 8.920002769572635e-7",
            "extra": "mean: 5.4050883443086395 usec\nrounds: 191976"
          },
          {
            "name": "tests/test_benchmarks.py::TestPhiScoringBenchmark::test_phi_score_100_outcomes",
            "value": 88451.54324165883,
            "unit": "iter/sec",
            "range": "stddev: 0.0000010185556088651709",
            "extra": "mean: 11.305625242375882 usec\nrounds: 92337"
          },
          {
            "name": "tests/test_benchmarks.py::TestRealisticScenarioBenchmark::test_realistic_25_agents",
            "value": 199.2329959681235,
            "unit": "iter/sec",
            "range": "stddev: 0.00007188797312737944",
            "extra": "mean: 5.019248920796212 msec\nrounds: 202"
          },
          {
            "name": "tests/test_benchmarks.py::TestPublishThroughputBenchmark::test_publish_100_intents",
            "value": 912.0765749608063,
            "unit": "iter/sec",
            "range": "stddev: 0.000014133627306944838",
            "extra": "mean: 1.0963991702593303 msec\nrounds: 928"
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
          "id": "ceda08c7e420627a843c366aae6ea7914ea9932c",
          "message": "Merge pull request #153 from Arete-Consortium/codex/animus-core-23-compat-clean\n\nCodex/animus core 23 compat clean",
          "timestamp": "2026-11-17T23:44:43-08:00",
          "tree_id": "b55023b03b9f1d32d7c2f7bd185194cf2f2612fd",
          "url": "https://github.com/Arete-Consortium/animus/commit/ceda08c7e420627a843c366aae6ea7914ea9932c"
        },
        "date": 1794988974445,
        "tool": "pytest",
        "benches": [
          {
            "name": "tests/test_benchmarks.py::TestMemorySerdeBenchmark::test_memory_serde_500",
            "value": 540.4221769436035,
            "unit": "iter/sec",
            "range": "stddev: 0.0005323784811624333",
            "extra": "mean: 1.8504051881356387 msec\nrounds: 590"
          },
          {
            "name": "tests/test_benchmarks.py::TestConversationSerdeBenchmark::test_conversation_serde_50msg",
            "value": 1242.9559062094268,
            "unit": "iter/sec",
            "range": "stddev: 0.0002111162722034469",
            "extra": "mean: 804.5337690615625 usec\nrounds: 1364"
          },
          {
            "name": "tests/test_benchmarks.py::TestDetectModeBenchmark::test_detect_mode_1000",
            "value": 403.42171855597275,
            "unit": "iter/sec",
            "range": "stddev: 0.0001477816347878091",
            "extra": "mean: 2.4787956473425585 msec\nrounds: 414"
          },
          {
            "name": "tests/test_benchmarks.py::TestEntitySearchBenchmark::test_entity_search_200",
            "value": 3874.12010955613,
            "unit": "iter/sec",
            "range": "stddev: 0.000007191503605517058",
            "extra": "mean: 258.12312776089254 usec\nrounds: 3984"
          },
          {
            "name": "tests/test_benchmarks.py::TestLocalSearchBenchmark::test_local_search_500",
            "value": 7215.7363205037445,
            "unit": "iter/sec",
            "range": "stddev: 0.000014166744627181824",
            "extra": "mean: 138.58599532780434 usec\nrounds: 7705"
          },
          {
            "name": "tests/test_benchmarks.py::TestWorkflowParseBenchmark::test_parse_20_step_workflow",
            "value": 31435.242610730453,
            "unit": "iter/sec",
            "range": "stddev: 0.0000026910757123611235",
            "extra": "mean: 31.81142936872544 usec\nrounds: 33328"
          },
          {
            "name": "tests/test_benchmarks.py::TestYAMLLoadBenchmark::test_load_yaml_10_steps",
            "value": 712.3153444542231,
            "unit": "iter/sec",
            "range": "stddev: 0.00004342379007899306",
            "extra": "mean: 1.4038726075263774 msec\nrounds: 744"
          },
          {
            "name": "tests/test_benchmarks.py::TestConditionEvalBenchmark::test_condition_evaluate_1000",
            "value": 9569.46934829776,
            "unit": "iter/sec",
            "range": "stddev: 0.000005468378138047524",
            "extra": "mean: 104.49900235877577 usec\nrounds: 10175"
          },
          {
            "name": "tests/test_benchmarks.py::TestCacheBenchmark::test_cache_set_get_1000",
            "value": 69.63685612293027,
            "unit": "iter/sec",
            "range": "stddev: 0.0003792040953713447",
            "extra": "mean: 14.360211756755577 msec\nrounds: 74"
          },
          {
            "name": "tests/test_benchmarks.py::TestTaskStoreBenchmark::test_record_query_100",
            "value": 9.713422867730335,
            "unit": "iter/sec",
            "range": "stddev: 0.01530498656435271",
            "extra": "mean: 102.95032076922877 msec\nrounds: 13"
          },
          {
            "name": "tests/test_benchmarks.py::TestBudgetBenchmark::test_budget_record_usage_500",
            "value": 977.9828716314086,
            "unit": "iter/sec",
            "range": "stddev: 0.0001738058275577168",
            "extra": "mean: 1.0225127954765343 msec\nrounds: 1017"
          },
          {
            "name": "tests/test_benchmarks.py::TestCheckpointBenchmark::test_checkpoint_lifecycle_20",
            "value": 37.62446955235589,
            "unit": "iter/sec",
            "range": "stddev: 0.008166111708418309",
            "extra": "mean: 26.57844780000052 msec\nrounds: 60"
          },
          {
            "name": "tests/test_benchmarks.py::TestSkillLookupBenchmark::test_skill_lookup_100",
            "value": 21130.746291306295,
            "unit": "iter/sec",
            "range": "stddev: 0.000002444653711595682",
            "extra": "mean: 47.32440521570336 usec\nrounds: 21665"
          },
          {
            "name": "tests/test_benchmarks.py::TestSessionControllerBenchmark::test_policy_check_latency",
            "value": 2911599.817028817,
            "unit": "iter/sec",
            "range": "stddev: 1.33030166521363e-7",
            "extra": "mean: 343.4537927057793 nsec\nrounds: 196967"
          },
          {
            "name": "tests/test_benchmarks.py::TestSessionControllerBenchmark::test_event_log_throughput",
            "value": 10319.307317918456,
            "unit": "iter/sec",
            "range": "stddev: 0.000018179481946371263",
            "extra": "mean: 96.90572915331235 usec\nrounds: 10973"
          },
          {
            "name": "tests/test_benchmarks.py::TestCheckpointBenchmark::test_checkpoint_save_latency",
            "value": 910.2738821199722,
            "unit": "iter/sec",
            "range": "stddev: 0.0009602815551843644",
            "extra": "mean: 1.0985704628491166 msec\nrounds: 1467"
          },
          {
            "name": "tests/test_benchmarks.py::TestCheckpointBenchmark::test_checkpoint_load_latency",
            "value": 12977.299419039979,
            "unit": "iter/sec",
            "range": "stddev: 0.00001366194734848214",
            "extra": "mean: 77.05763485219616 usec\nrounds: 14857"
          },
          {
            "name": "tests/test_benchmarks.py::TestCheckpointBenchmark::test_checkpoint_list_recent",
            "value": 10318.824334726029,
            "unit": "iter/sec",
            "range": "stddev: 0.000030686263911676554",
            "extra": "mean: 96.91026492569425 usec\nrounds: 11909"
          },
          {
            "name": "tests/test_benchmarks.py::TestContextManagerBenchmark::test_finalize_summary_latency",
            "value": 540723.5105234515,
            "unit": "iter/sec",
            "range": "stddev: 2.107517883639188e-7",
            "extra": "mean: 1.8493739971319951 usec\nrounds: 57186"
          },
          {
            "name": "tests/test_benchmarks.py::TestResolverBenchmark::test_resolve_50_intents",
            "value": 1323.643981538159,
            "unit": "iter/sec",
            "range": "stddev: 0.00007019542746453113",
            "extra": "mean: 755.4901574348836 usec\nrounds: 1372"
          },
          {
            "name": "tests/test_benchmarks.py::TestStructuralOverlapBenchmark::test_structural_overlaps_1000",
            "value": 515.6342511995052,
            "unit": "iter/sec",
            "range": "stddev: 0.00006534970782517765",
            "extra": "mean: 1.939359143954709 msec\nrounds: 521"
          },
          {
            "name": "tests/test_benchmarks.py::TestConstraintBenchmark::test_validate_20_constraints",
            "value": 364149.6052372684,
            "unit": "iter/sec",
            "range": "stddev: 2.8401352383280394e-7",
            "extra": "mean: 2.7461240809211684 usec\nrounds: 187688"
          },
          {
            "name": "tests/test_benchmarks.py::TestPhiScoringBenchmark::test_phi_score_100_outcomes",
            "value": 185747.50475261107,
            "unit": "iter/sec",
            "range": "stddev: 5.112886656374767e-7",
            "extra": "mean: 5.383652401316809 usec\nrounds: 193499"
          },
          {
            "name": "tests/test_benchmarks.py::TestRealisticScenarioBenchmark::test_realistic_25_agents",
            "value": 387.89234515338325,
            "unit": "iter/sec",
            "range": "stddev: 0.00005893008446120348",
            "extra": "mean: 2.578034891625852 msec\nrounds: 406"
          },
          {
            "name": "tests/test_benchmarks.py::TestPublishThroughputBenchmark::test_publish_100_intents",
            "value": 1841.890805685805,
            "unit": "iter/sec",
            "range": "stddev: 0.000020054350023964746",
            "extra": "mean: 542.920349519668 usec\nrounds: 1874"
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
          "id": "8052308e6b0534071351dac4def32a8e24ee4970",
          "message": "Fix packaged PWA and remote authentication\n\n* Fix packaged PWA and remote auth\n\n* Keep WebSocket token out of request URL",
          "timestamp": "2026-11-20T17:14:07-08:00",
          "tree_id": "3620e8d8dabfb52c23201dc4f597b691f9d28f34",
          "url": "https://github.com/Arete-Consortium/animus/commit/8052308e6b0534071351dac4def32a8e24ee4970"
        },
        "date": 1795224685603,
        "tool": "pytest",
        "benches": [
          {
            "name": "tests/test_benchmarks.py::TestMemorySerdeBenchmark::test_memory_serde_500",
            "value": 313.2912616819249,
            "unit": "iter/sec",
            "range": "stddev: 0.00001703670081004178",
            "extra": "mean: 3.191917944443882 msec\nrounds: 306"
          },
          {
            "name": "tests/test_benchmarks.py::TestConversationSerdeBenchmark::test_conversation_serde_50msg",
            "value": 687.3786251650026,
            "unit": "iter/sec",
            "range": "stddev: 0.000017082135587786655",
            "extra": "mean: 1.4548022929283753 msec\nrounds: 693"
          },
          {
            "name": "tests/test_benchmarks.py::TestDetectModeBenchmark::test_detect_mode_1000",
            "value": 227.4953452556435,
            "unit": "iter/sec",
            "range": "stddev: 0.00008503440084587415",
            "extra": "mean: 4.395694333333587 msec\nrounds: 231"
          },
          {
            "name": "tests/test_benchmarks.py::TestEntitySearchBenchmark::test_entity_search_200",
            "value": 1926.345693036649,
            "unit": "iter/sec",
            "range": "stddev: 0.000010276368921459054",
            "extra": "mean: 519.1176244299236 usec\nrounds: 1973"
          },
          {
            "name": "tests/test_benchmarks.py::TestLocalSearchBenchmark::test_local_search_500",
            "value": 3549.9625349291114,
            "unit": "iter/sec",
            "range": "stddev: 0.000006368205665047535",
            "extra": "mean: 281.6931137049222 usec\nrounds: 3641"
          },
          {
            "name": "tests/test_benchmarks.py::TestWorkflowParseBenchmark::test_parse_20_step_workflow",
            "value": 17612.723422148974,
            "unit": "iter/sec",
            "range": "stddev: 0.0000028594054287056385",
            "extra": "mean: 56.77713639348045 usec\nrounds: 18234"
          },
          {
            "name": "tests/test_benchmarks.py::TestYAMLLoadBenchmark::test_load_yaml_10_steps",
            "value": 345.3680801874889,
            "unit": "iter/sec",
            "range": "stddev: 0.00004108560188847351",
            "extra": "mean: 2.895461559322834 msec\nrounds: 354"
          },
          {
            "name": "tests/test_benchmarks.py::TestConditionEvalBenchmark::test_condition_evaluate_1000",
            "value": 4831.45491424261,
            "unit": "iter/sec",
            "range": "stddev: 0.000023787186482480284",
            "extra": "mean: 206.97699093747255 usec\nrounds: 5076"
          },
          {
            "name": "tests/test_benchmarks.py::TestCacheBenchmark::test_cache_set_get_1000",
            "value": 36.021323653937884,
            "unit": "iter/sec",
            "range": "stddev: 0.0007594090262870141",
            "extra": "mean: 27.761334081088915 msec\nrounds: 37"
          },
          {
            "name": "tests/test_benchmarks.py::TestTaskStoreBenchmark::test_record_query_100",
            "value": 11.052189239794162,
            "unit": "iter/sec",
            "range": "stddev: 0.004282754109966843",
            "extra": "mean: 90.47981158334058 msec\nrounds: 12"
          },
          {
            "name": "tests/test_benchmarks.py::TestBudgetBenchmark::test_budget_record_usage_500",
            "value": 557.0457187439108,
            "unit": "iter/sec",
            "range": "stddev: 0.00019424508466178304",
            "extra": "mean: 1.7951847870851825 msec\nrounds: 573"
          },
          {
            "name": "tests/test_benchmarks.py::TestCheckpointBenchmark::test_checkpoint_lifecycle_20",
            "value": 50.18534434644835,
            "unit": "iter/sec",
            "range": "stddev: 0.0017484375991586424",
            "extra": "mean: 19.926136066669642 msec\nrounds: 60"
          },
          {
            "name": "tests/test_benchmarks.py::TestSkillLookupBenchmark::test_skill_lookup_100",
            "value": 9404.576858227163,
            "unit": "iter/sec",
            "range": "stddev: 0.000005684842005779724",
            "extra": "mean: 106.33120607921833 usec\nrounds: 9540"
          },
          {
            "name": "tests/test_benchmarks.py::TestSessionControllerBenchmark::test_policy_check_latency",
            "value": 1424544.7425963364,
            "unit": "iter/sec",
            "range": "stddev: 1.0140479080424494e-7",
            "extra": "mean: 701.9786533186926 nsec\nrounds: 147667"
          },
          {
            "name": "tests/test_benchmarks.py::TestSessionControllerBenchmark::test_event_log_throughput",
            "value": 6177.16932524445,
            "unit": "iter/sec",
            "range": "stddev: 0.000007532416721786417",
            "extra": "mean: 161.88644787722842 usec\nrounds: 6571"
          },
          {
            "name": "tests/test_benchmarks.py::TestCheckpointBenchmark::test_checkpoint_save_latency",
            "value": 1155.789553612686,
            "unit": "iter/sec",
            "range": "stddev: 0.0002709526947570321",
            "extra": "mean: 865.2094119334009 usec\nrounds: 1391"
          },
          {
            "name": "tests/test_benchmarks.py::TestCheckpointBenchmark::test_checkpoint_load_latency",
            "value": 5924.1922823377445,
            "unit": "iter/sec",
            "range": "stddev: 0.000014403835690386047",
            "extra": "mean: 168.79938265700423 usec\nrounds: 6481"
          },
          {
            "name": "tests/test_benchmarks.py::TestCheckpointBenchmark::test_checkpoint_list_recent",
            "value": 5213.543394835108,
            "unit": "iter/sec",
            "range": "stddev: 0.00001739055373823072",
            "extra": "mean: 191.80812822823495 usec\nrounds: 5576"
          },
          {
            "name": "tests/test_benchmarks.py::TestContextManagerBenchmark::test_finalize_summary_latency",
            "value": 266620.41726158164,
            "unit": "iter/sec",
            "range": "stddev: 5.641863793945122e-7",
            "extra": "mean: 3.7506504950777977 usec\nrounds: 137855"
          },
          {
            "name": "tests/test_benchmarks.py::TestResolverBenchmark::test_resolve_50_intents",
            "value": 695.620045724236,
            "unit": "iter/sec",
            "range": "stddev: 0.00003211002920623091",
            "extra": "mean: 1.4375663929564633 msec\nrounds: 710"
          },
          {
            "name": "tests/test_benchmarks.py::TestStructuralOverlapBenchmark::test_structural_overlaps_1000",
            "value": 295.3538469119831,
            "unit": "iter/sec",
            "range": "stddev: 0.00004821902623700015",
            "extra": "mean: 3.3857693422832074 msec\nrounds: 298"
          },
          {
            "name": "tests/test_benchmarks.py::TestConstraintBenchmark::test_validate_20_constraints",
            "value": 186152.06367529376,
            "unit": "iter/sec",
            "range": "stddev: 7.921489794100952e-7",
            "extra": "mean: 5.371952264490102 usec\nrounds: 189754"
          },
          {
            "name": "tests/test_benchmarks.py::TestPhiScoringBenchmark::test_phi_score_100_outcomes",
            "value": 88840.97204613533,
            "unit": "iter/sec",
            "range": "stddev: 0.0000011106421899119231",
            "extra": "mean: 11.256067746317516 usec\nrounds: 92507"
          },
          {
            "name": "tests/test_benchmarks.py::TestRealisticScenarioBenchmark::test_realistic_25_agents",
            "value": 201.5772342193745,
            "unit": "iter/sec",
            "range": "stddev: 0.00003521287811220999",
            "extra": "mean: 4.9608776699044785 msec\nrounds: 206"
          },
          {
            "name": "tests/test_benchmarks.py::TestPublishThroughputBenchmark::test_publish_100_intents",
            "value": 913.5726950344938,
            "unit": "iter/sec",
            "range": "stddev: 0.000015559807289029074",
            "extra": "mean: 1.0946036428576085 msec\nrounds: 924"
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
          "id": "1e2c9085e2ab3b5ad359f211f9082ab08314b1c4",
          "message": "Fix mobile PWA tab navigation (#155)",
          "timestamp": "2026-11-20T19:50:04-08:00",
          "tree_id": "f829a0711a533c963d17fc4bc59df319dca70d20",
          "url": "https://github.com/Arete-Consortium/animus/commit/1e2c9085e2ab3b5ad359f211f9082ab08314b1c4"
        },
        "date": 1795234043130,
        "tool": "pytest",
        "benches": [
          {
            "name": "tests/test_benchmarks.py::TestMemorySerdeBenchmark::test_memory_serde_500",
            "value": 546.3854725333047,
            "unit": "iter/sec",
            "range": "stddev: 0.000033642239443325845",
            "extra": "mean: 1.8302097150634717 msec\nrounds: 551"
          },
          {
            "name": "tests/test_benchmarks.py::TestConversationSerdeBenchmark::test_conversation_serde_50msg",
            "value": 1248.4110902043249,
            "unit": "iter/sec",
            "range": "stddev: 0.00004903946457572071",
            "extra": "mean: 801.018196527181 usec\nrounds: 1267"
          },
          {
            "name": "tests/test_benchmarks.py::TestDetectModeBenchmark::test_detect_mode_1000",
            "value": 423.41398065469366,
            "unit": "iter/sec",
            "range": "stddev: 0.00009563316893185349",
            "extra": "mean: 2.3617547971698385 msec\nrounds: 424"
          },
          {
            "name": "tests/test_benchmarks.py::TestEntitySearchBenchmark::test_entity_search_200",
            "value": 3737.91672211666,
            "unit": "iter/sec",
            "range": "stddev: 0.000010178122430208363",
            "extra": "mean: 267.5286996318454 usec\nrounds: 4075"
          },
          {
            "name": "tests/test_benchmarks.py::TestLocalSearchBenchmark::test_local_search_500",
            "value": 6411.579797304931,
            "unit": "iter/sec",
            "range": "stddev: 0.000008294069006030093",
            "extra": "mean: 155.96780070028043 usec\nrounds: 7426"
          },
          {
            "name": "tests/test_benchmarks.py::TestWorkflowParseBenchmark::test_parse_20_step_workflow",
            "value": 30791.016623417974,
            "unit": "iter/sec",
            "range": "stddev: 0.0000016846496543643187",
            "extra": "mean: 32.477004972919744 usec\nrounds: 31370"
          },
          {
            "name": "tests/test_benchmarks.py::TestYAMLLoadBenchmark::test_load_yaml_10_steps",
            "value": 670.5074415408283,
            "unit": "iter/sec",
            "range": "stddev: 0.00009134873089290966",
            "extra": "mean: 1.4914077578348672 msec\nrounds: 702"
          },
          {
            "name": "tests/test_benchmarks.py::TestConditionEvalBenchmark::test_condition_evaluate_1000",
            "value": 8817.978394429816,
            "unit": "iter/sec",
            "range": "stddev: 0.000003865486063586953",
            "extra": "mean: 113.40467795109194 usec\nrounds: 10132"
          },
          {
            "name": "tests/test_benchmarks.py::TestCacheBenchmark::test_cache_set_get_1000",
            "value": 68.3515689148618,
            "unit": "iter/sec",
            "range": "stddev: 0.000359960190800333",
            "extra": "mean: 14.630242083332313 msec\nrounds: 72"
          },
          {
            "name": "tests/test_benchmarks.py::TestTaskStoreBenchmark::test_record_query_100",
            "value": 12.892596373672824,
            "unit": "iter/sec",
            "range": "stddev: 0.018706323914404188",
            "extra": "mean: 77.56389566666637 msec\nrounds: 15"
          },
          {
            "name": "tests/test_benchmarks.py::TestBudgetBenchmark::test_budget_record_usage_500",
            "value": 970.1790207739946,
            "unit": "iter/sec",
            "range": "stddev: 0.0001413597301314827",
            "extra": "mean: 1.030737604697136 msec\nrounds: 1022"
          },
          {
            "name": "tests/test_benchmarks.py::TestCheckpointBenchmark::test_checkpoint_lifecycle_20",
            "value": 58.4690444193286,
            "unit": "iter/sec",
            "range": "stddev: 0.002026032631375091",
            "extra": "mean: 17.103067271429904 msec\nrounds: 70"
          },
          {
            "name": "tests/test_benchmarks.py::TestSkillLookupBenchmark::test_skill_lookup_100",
            "value": 17623.72571689368,
            "unit": "iter/sec",
            "range": "stddev: 0.000017482935296883907",
            "extra": "mean: 56.741691062601134 usec\nrounds: 19648"
          },
          {
            "name": "tests/test_benchmarks.py::TestSessionControllerBenchmark::test_policy_check_latency",
            "value": 2568864.030727667,
            "unit": "iter/sec",
            "range": "stddev: 5.926671333526208e-8",
            "extra": "mean: 389.27712328812356 nsec\nrounds: 197707"
          },
          {
            "name": "tests/test_benchmarks.py::TestSessionControllerBenchmark::test_event_log_throughput",
            "value": 9691.08398168144,
            "unit": "iter/sec",
            "range": "stddev: 0.00002760868652131237",
            "extra": "mean: 103.18763121754479 usec\nrounds: 10635"
          },
          {
            "name": "tests/test_benchmarks.py::TestCheckpointBenchmark::test_checkpoint_save_latency",
            "value": 955.7508485969424,
            "unit": "iter/sec",
            "range": "stddev: 0.002501647640251232",
            "extra": "mean: 1.0462977892910228 msec\nrounds: 1438"
          },
          {
            "name": "tests/test_benchmarks.py::TestCheckpointBenchmark::test_checkpoint_load_latency",
            "value": 12696.483542254175,
            "unit": "iter/sec",
            "range": "stddev: 0.000006021820746955892",
            "extra": "mean: 78.76196560031588 usec\nrounds: 14099"
          },
          {
            "name": "tests/test_benchmarks.py::TestCheckpointBenchmark::test_checkpoint_list_recent",
            "value": 10205.618115448864,
            "unit": "iter/sec",
            "range": "stddev: 0.000007049653827769003",
            "extra": "mean: 97.98524584084126 usec\nrounds: 11060"
          },
          {
            "name": "tests/test_benchmarks.py::TestContextManagerBenchmark::test_finalize_summary_latency",
            "value": 519030.5800586339,
            "unit": "iter/sec",
            "range": "stddev: 1.208509678607658e-7",
            "extra": "mean: 1.9266687521321615 usec\nrounds: 53082"
          },
          {
            "name": "tests/test_benchmarks.py::TestResolverBenchmark::test_resolve_50_intents",
            "value": 1254.9197013775467,
            "unit": "iter/sec",
            "range": "stddev: 0.00002977939809924515",
            "extra": "mean: 796.8637347093069 usec\nrounds: 1308"
          },
          {
            "name": "tests/test_benchmarks.py::TestStructuralOverlapBenchmark::test_structural_overlaps_1000",
            "value": 500.698549777505,
            "unit": "iter/sec",
            "range": "stddev: 0.000050418997653354064",
            "extra": "mean: 1.997209699217961 msec\nrounds: 512"
          },
          {
            "name": "tests/test_benchmarks.py::TestConstraintBenchmark::test_validate_20_constraints",
            "value": 354639.73451396084,
            "unit": "iter/sec",
            "range": "stddev: 2.7352982294384546e-7",
            "extra": "mean: 2.819762995171749 usec\nrounds: 182549"
          },
          {
            "name": "tests/test_benchmarks.py::TestPhiScoringBenchmark::test_phi_score_100_outcomes",
            "value": 185347.06746252874,
            "unit": "iter/sec",
            "range": "stddev: 5.700995014991073e-7",
            "extra": "mean: 5.3952836356699745 usec\nrounds: 195046"
          },
          {
            "name": "tests/test_benchmarks.py::TestRealisticScenarioBenchmark::test_realistic_25_agents",
            "value": 381.43745564356766,
            "unit": "iter/sec",
            "range": "stddev: 0.00006249130148588718",
            "extra": "mean: 2.621661782828284 msec\nrounds: 396"
          },
          {
            "name": "tests/test_benchmarks.py::TestPublishThroughputBenchmark::test_publish_100_intents",
            "value": 1725.5378344568605,
            "unit": "iter/sec",
            "range": "stddev: 0.0000225542868367013",
            "extra": "mean: 579.5294545452637 usec\nrounds: 1837"
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
          "id": "90d909bc4637bdd31952bb581378701152ca1a6f",
          "message": "Add Forgehand relay status to dashboard (#156)\n\n* Add Forgehand relay status to dashboard\n\n* Fix relay status CI and CodeQL findings\n\n* Avoid permissive chmod in relay status test",
          "timestamp": "2026-11-21T15:47:52-08:00",
          "tree_id": "08c6995c65f6546e8be18fa3908c41f61ce07d69",
          "url": "https://github.com/Arete-Consortium/animus/commit/90d909bc4637bdd31952bb581378701152ca1a6f"
        },
        "date": 1795305906332,
        "tool": "pytest",
        "benches": [
          {
            "name": "tests/test_benchmarks.py::TestMemorySerdeBenchmark::test_memory_serde_500",
            "value": 548.224808418713,
            "unit": "iter/sec",
            "range": "stddev: 0.00009781360806808923",
            "extra": "mean: 1.8240692224132962 msec\nrounds: 580"
          },
          {
            "name": "tests/test_benchmarks.py::TestConversationSerdeBenchmark::test_conversation_serde_50msg",
            "value": 1290.867389112917,
            "unit": "iter/sec",
            "range": "stddev: 0.000013043517030565316",
            "extra": "mean: 774.672912519077 usec\nrounds: 1326"
          },
          {
            "name": "tests/test_benchmarks.py::TestDetectModeBenchmark::test_detect_mode_1000",
            "value": 414.83577629506516,
            "unit": "iter/sec",
            "range": "stddev: 0.00005076560093319723",
            "extra": "mean: 2.410592473318208 msec\nrounds: 431"
          },
          {
            "name": "tests/test_benchmarks.py::TestEntitySearchBenchmark::test_entity_search_200",
            "value": 4059.8688706569515,
            "unit": "iter/sec",
            "range": "stddev: 0.000008150721669106608",
            "extra": "mean: 246.31337411599307 usec\nrounds: 4242"
          },
          {
            "name": "tests/test_benchmarks.py::TestLocalSearchBenchmark::test_local_search_500",
            "value": 7322.573870811249,
            "unit": "iter/sec",
            "range": "stddev: 0.00000611131441785166",
            "extra": "mean: 136.56400299164378 usec\nrounds: 7688"
          },
          {
            "name": "tests/test_benchmarks.py::TestWorkflowParseBenchmark::test_parse_20_step_workflow",
            "value": 30358.389722869975,
            "unit": "iter/sec",
            "range": "stddev: 0.00001349036145258771",
            "extra": "mean: 32.939823525839614 usec\nrounds: 33053"
          },
          {
            "name": "tests/test_benchmarks.py::TestYAMLLoadBenchmark::test_load_yaml_10_steps",
            "value": 687.6068370859601,
            "unit": "iter/sec",
            "range": "stddev: 0.00003217556867226895",
            "extra": "mean: 1.4543194541781244 msec\nrounds: 742"
          },
          {
            "name": "tests/test_benchmarks.py::TestConditionEvalBenchmark::test_condition_evaluate_1000",
            "value": 9472.34296090994,
            "unit": "iter/sec",
            "range": "stddev: 0.00002757324042638855",
            "extra": "mean: 105.57050184170456 usec\nrounds: 10316"
          },
          {
            "name": "tests/test_benchmarks.py::TestCacheBenchmark::test_cache_set_get_1000",
            "value": 68.94381137172122,
            "unit": "iter/sec",
            "range": "stddev: 0.0014459165138574373",
            "extra": "mean: 14.504565095891572 msec\nrounds: 73"
          },
          {
            "name": "tests/test_benchmarks.py::TestTaskStoreBenchmark::test_record_query_100",
            "value": 6.822569617601588,
            "unit": "iter/sec",
            "range": "stddev: 0.2573465708718507",
            "extra": "mean: 146.5723409285695 msec\nrounds: 14"
          },
          {
            "name": "tests/test_benchmarks.py::TestBudgetBenchmark::test_budget_record_usage_500",
            "value": 1005.8958644973123,
            "unit": "iter/sec",
            "range": "stddev: 0.00010961962537522652",
            "extra": "mean: 994.138692974686 usec\nrounds: 1039"
          },
          {
            "name": "tests/test_benchmarks.py::TestCheckpointBenchmark::test_checkpoint_lifecycle_20",
            "value": 61.14492158935261,
            "unit": "iter/sec",
            "range": "stddev: 0.0017187136928514854",
            "extra": "mean: 16.3545879855071 msec\nrounds: 69"
          },
          {
            "name": "tests/test_benchmarks.py::TestSkillLookupBenchmark::test_skill_lookup_100",
            "value": 20107.198349969443,
            "unit": "iter/sec",
            "range": "stddev: 0.000001985460429359067",
            "extra": "mean: 49.73343290272559 usec\nrounds: 20977"
          },
          {
            "name": "tests/test_benchmarks.py::TestSessionControllerBenchmark::test_policy_check_latency",
            "value": 2837406.2996836784,
            "unit": "iter/sec",
            "range": "stddev: 5.782029860378056e-8",
            "extra": "mean: 352.4345456311571 nsec\nrounds: 195008"
          },
          {
            "name": "tests/test_benchmarks.py::TestSessionControllerBenchmark::test_event_log_throughput",
            "value": 10292.852630761286,
            "unit": "iter/sec",
            "range": "stddev: 0.000004971324875961818",
            "extra": "mean: 97.15479623320299 usec\nrounds: 10831"
          },
          {
            "name": "tests/test_benchmarks.py::TestCheckpointBenchmark::test_checkpoint_save_latency",
            "value": 1314.634909594563,
            "unit": "iter/sec",
            "range": "stddev: 0.0002376781720991909",
            "extra": "mean: 760.6674618951073 usec\nrounds: 1509"
          },
          {
            "name": "tests/test_benchmarks.py::TestCheckpointBenchmark::test_checkpoint_load_latency",
            "value": 12319.12848613839,
            "unit": "iter/sec",
            "range": "stddev: 0.000027254447558845186",
            "extra": "mean: 81.17457343879563 usec\nrounds: 14427"
          },
          {
            "name": "tests/test_benchmarks.py::TestCheckpointBenchmark::test_checkpoint_list_recent",
            "value": 10619.147501231386,
            "unit": "iter/sec",
            "range": "stddev: 0.000004887065946863142",
            "extra": "mean: 94.16951783408612 usec\nrounds: 11635"
          },
          {
            "name": "tests/test_benchmarks.py::TestContextManagerBenchmark::test_finalize_summary_latency",
            "value": 535636.0850417103,
            "unit": "iter/sec",
            "range": "stddev: 1.583201706043033e-7",
            "extra": "mean: 1.866939192347598 usec\nrounds: 55197"
          },
          {
            "name": "tests/test_benchmarks.py::TestResolverBenchmark::test_resolve_50_intents",
            "value": 1332.760422487655,
            "unit": "iter/sec",
            "range": "stddev: 0.00002884793647417903",
            "extra": "mean: 750.3224008809151 usec\nrounds: 1362"
          },
          {
            "name": "tests/test_benchmarks.py::TestStructuralOverlapBenchmark::test_structural_overlaps_1000",
            "value": 514.3576227424944,
            "unit": "iter/sec",
            "range": "stddev: 0.00006775174244798349",
            "extra": "mean: 1.9441726063436513 msec\nrounds: 536"
          },
          {
            "name": "tests/test_benchmarks.py::TestConstraintBenchmark::test_validate_20_constraints",
            "value": 364134.67506715754,
            "unit": "iter/sec",
            "range": "stddev: 3.8271551905763776e-7",
            "extra": "mean: 2.746236676898649 usec\nrounds: 188751"
          },
          {
            "name": "tests/test_benchmarks.py::TestPhiScoringBenchmark::test_phi_score_100_outcomes",
            "value": 170004.22893039172,
            "unit": "iter/sec",
            "range": "stddev: 0.000004139207032762583",
            "extra": "mean: 5.882206615045149 usec\nrounds: 186637"
          },
          {
            "name": "tests/test_benchmarks.py::TestRealisticScenarioBenchmark::test_realistic_25_agents",
            "value": 365.1730645325782,
            "unit": "iter/sec",
            "range": "stddev: 0.0002515383009724434",
            "extra": "mean: 2.7384276035802384 msec\nrounds: 391"
          },
          {
            "name": "tests/test_benchmarks.py::TestPublishThroughputBenchmark::test_publish_100_intents",
            "value": 1661.0628450771048,
            "unit": "iter/sec",
            "range": "stddev: 0.00007971732485365776",
            "extra": "mean: 602.0241816639882 usec\nrounds: 1767"
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
          "id": "1a1372bfc6b8fefe418aa5045b11ba191a6bb13f",
          "message": "feat: add durable knowledge edge pilot (#157)\n\n* feat: add durable knowledge edge pilot\n\n* fix: satisfy knowledge edge CI contracts\n\n* test: register knowledge edge type module\n\n* fix: annotate knowledge edge ORM columns\n\n* Harden knowledge edge visibility and integrity",
          "timestamp": "2026-11-22T17:48:29-08:00",
          "tree_id": "bbf670a281e07063aece7729e9e4790415777079",
          "url": "https://github.com/Arete-Consortium/animus/commit/1a1372bfc6b8fefe418aa5045b11ba191a6bb13f"
        },
        "date": 1795399613368,
        "tool": "pytest",
        "benches": [
          {
            "name": "tests/test_benchmarks.py::TestMemorySerdeBenchmark::test_memory_serde_500",
            "value": 299.000827761256,
            "unit": "iter/sec",
            "range": "stddev: 0.000050678223096563154",
            "extra": "mean: 3.344472346405919 msec\nrounds: 306"
          },
          {
            "name": "tests/test_benchmarks.py::TestConversationSerdeBenchmark::test_conversation_serde_50msg",
            "value": 664.0762680438681,
            "unit": "iter/sec",
            "range": "stddev: 0.000020386689221912362",
            "extra": "mean: 1.5058511320478947 msec\nrounds: 674"
          },
          {
            "name": "tests/test_benchmarks.py::TestDetectModeBenchmark::test_detect_mode_1000",
            "value": 207.2220978060099,
            "unit": "iter/sec",
            "range": "stddev: 0.0006830685867284307",
            "extra": "mean: 4.825740162789712 msec\nrounds: 215"
          },
          {
            "name": "tests/test_benchmarks.py::TestEntitySearchBenchmark::test_entity_search_200",
            "value": 1898.827618173915,
            "unit": "iter/sec",
            "range": "stddev: 0.000016920875522785073",
            "extra": "mean: 526.640749496624 usec\nrounds: 1988"
          },
          {
            "name": "tests/test_benchmarks.py::TestLocalSearchBenchmark::test_local_search_500",
            "value": 3553.8913032850996,
            "unit": "iter/sec",
            "range": "stddev: 0.000028989329726918945",
            "extra": "mean: 281.38170660302217 usec\nrounds: 3756"
          },
          {
            "name": "tests/test_benchmarks.py::TestWorkflowParseBenchmark::test_parse_20_step_workflow",
            "value": 17517.964528927554,
            "unit": "iter/sec",
            "range": "stddev: 0.000003791696992591274",
            "extra": "mean: 57.08425761159021 usec\nrounds: 17802"
          },
          {
            "name": "tests/test_benchmarks.py::TestYAMLLoadBenchmark::test_load_yaml_10_steps",
            "value": 333.1763826474215,
            "unit": "iter/sec",
            "range": "stddev: 0.00006775768017521618",
            "extra": "mean: 3.001413221591501 msec\nrounds: 352"
          },
          {
            "name": "tests/test_benchmarks.py::TestConditionEvalBenchmark::test_condition_evaluate_1000",
            "value": 5171.948187170814,
            "unit": "iter/sec",
            "range": "stddev: 0.000007194543247793191",
            "extra": "mean: 193.35073821515317 usec\nrounds: 5367"
          },
          {
            "name": "tests/test_benchmarks.py::TestCacheBenchmark::test_cache_set_get_1000",
            "value": 35.90162346976393,
            "unit": "iter/sec",
            "range": "stddev: 0.00019572032340388804",
            "extra": "mean: 27.853893594594464 msec\nrounds: 37"
          },
          {
            "name": "tests/test_benchmarks.py::TestTaskStoreBenchmark::test_record_query_100",
            "value": 11.181327935224287,
            "unit": "iter/sec",
            "range": "stddev: 0.005782517844546376",
            "extra": "mean: 89.43481541666642 msec\nrounds: 12"
          },
          {
            "name": "tests/test_benchmarks.py::TestBudgetBenchmark::test_budget_record_usage_500",
            "value": 541.1021315897286,
            "unit": "iter/sec",
            "range": "stddev: 0.00008381733666353543",
            "extra": "mean: 1.8480799494580709 msec\nrounds: 554"
          },
          {
            "name": "tests/test_benchmarks.py::TestCheckpointBenchmark::test_checkpoint_lifecycle_20",
            "value": 52.18352697347341,
            "unit": "iter/sec",
            "range": "stddev: 0.0013250650182206737",
            "extra": "mean: 19.16313553333282 msec\nrounds: 60"
          },
          {
            "name": "tests/test_benchmarks.py::TestSkillLookupBenchmark::test_skill_lookup_100",
            "value": 8913.474605182691,
            "unit": "iter/sec",
            "range": "stddev: 0.000005958378197532507",
            "extra": "mean: 112.18969529778605 usec\nrounds: 9081"
          },
          {
            "name": "tests/test_benchmarks.py::TestSessionControllerBenchmark::test_policy_check_latency",
            "value": 1467834.801457057,
            "unit": "iter/sec",
            "range": "stddev: 8.642947907624819e-8",
            "extra": "mean: 681.2755761120685 nsec\nrounds: 151012"
          },
          {
            "name": "tests/test_benchmarks.py::TestSessionControllerBenchmark::test_event_log_throughput",
            "value": 5935.042266646922,
            "unit": "iter/sec",
            "range": "stddev: 0.000008028077588424577",
            "extra": "mean: 168.4907967074955 usec\nrounds: 6257"
          },
          {
            "name": "tests/test_benchmarks.py::TestCheckpointBenchmark::test_checkpoint_save_latency",
            "value": 1124.0830585692759,
            "unit": "iter/sec",
            "range": "stddev: 0.0001871565324108855",
            "extra": "mean: 889.6139768112796 usec\nrounds: 1380"
          },
          {
            "name": "tests/test_benchmarks.py::TestCheckpointBenchmark::test_checkpoint_load_latency",
            "value": 5767.67053218662,
            "unit": "iter/sec",
            "range": "stddev: 0.000017801644851514103",
            "extra": "mean: 173.38022246927534 usec\nrounds: 6311"
          },
          {
            "name": "tests/test_benchmarks.py::TestCheckpointBenchmark::test_checkpoint_list_recent",
            "value": 5052.817454780407,
            "unit": "iter/sec",
            "range": "stddev: 0.000014941485671822164",
            "extra": "mean: 197.90938599096083 usec\nrounds: 5368"
          },
          {
            "name": "tests/test_benchmarks.py::TestContextManagerBenchmark::test_finalize_summary_latency",
            "value": 269417.190483891,
            "unit": "iter/sec",
            "range": "stddev: 7.272927891669302e-7",
            "extra": "mean: 3.711715641470146 usec\nrounds: 136931"
          },
          {
            "name": "tests/test_benchmarks.py::TestResolverBenchmark::test_resolve_50_intents",
            "value": 702.5718582210392,
            "unit": "iter/sec",
            "range": "stddev: 0.00007072577380875535",
            "extra": "mean: 1.4233419518568102 msec\nrounds: 727"
          },
          {
            "name": "tests/test_benchmarks.py::TestStructuralOverlapBenchmark::test_structural_overlaps_1000",
            "value": 286.8532318080259,
            "unit": "iter/sec",
            "range": "stddev: 0.00005067354207705852",
            "extra": "mean: 3.486103306896823 msec\nrounds: 290"
          },
          {
            "name": "tests/test_benchmarks.py::TestConstraintBenchmark::test_validate_20_constraints",
            "value": 184376.11025882926,
            "unit": "iter/sec",
            "range": "stddev: 8.010566049788568e-7",
            "extra": "mean: 5.423696153456045 usec\nrounds: 191939"
          },
          {
            "name": "tests/test_benchmarks.py::TestPhiScoringBenchmark::test_phi_score_100_outcomes",
            "value": 88987.45378410554,
            "unit": "iter/sec",
            "range": "stddev: 0.0000010715246693899357",
            "extra": "mean: 11.237539197672994 usec\nrounds: 90082"
          },
          {
            "name": "tests/test_benchmarks.py::TestRealisticScenarioBenchmark::test_realistic_25_agents",
            "value": 198.6755080786243,
            "unit": "iter/sec",
            "range": "stddev: 0.00006091751666648085",
            "extra": "mean: 5.033333044777002 msec\nrounds: 201"
          },
          {
            "name": "tests/test_benchmarks.py::TestPublishThroughputBenchmark::test_publish_100_intents",
            "value": 902.6089931667357,
            "unit": "iter/sec",
            "range": "stddev: 0.00001553882555262054",
            "extra": "mean: 1.1078994421400292 msec\nrounds: 916"
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
          "id": "3b337d1e756f32ce3347316d680f529b5ae1a772",
          "message": "Require unverified status for scoped knowledge edge writes (#158)",
          "timestamp": "2026-11-23T12:41:58-08:00",
          "tree_id": "a05849e653626002116f21dca550387acd12377b",
          "url": "https://github.com/Arete-Consortium/animus/commit/3b337d1e756f32ce3347316d680f529b5ae1a772"
        },
        "date": 1795467726910,
        "tool": "pytest",
        "benches": [
          {
            "name": "tests/test_benchmarks.py::TestMemorySerdeBenchmark::test_memory_serde_500",
            "value": 397.81739251508947,
            "unit": "iter/sec",
            "range": "stddev: 0.00031224806096508253",
            "extra": "mean: 2.513716139150626 msec\nrounds: 424"
          },
          {
            "name": "tests/test_benchmarks.py::TestConversationSerdeBenchmark::test_conversation_serde_50msg",
            "value": 869.4580505226756,
            "unit": "iter/sec",
            "range": "stddev: 0.00009312380483601364",
            "extra": "mean: 1.150141745652765 msec\nrounds: 920"
          },
          {
            "name": "tests/test_benchmarks.py::TestDetectModeBenchmark::test_detect_mode_1000",
            "value": 299.0953272894788,
            "unit": "iter/sec",
            "range": "stddev: 0.0004535380841423673",
            "extra": "mean: 3.343415656347423 msec\nrounds: 323"
          },
          {
            "name": "tests/test_benchmarks.py::TestEntitySearchBenchmark::test_entity_search_200",
            "value": 2715.7715631192054,
            "unit": "iter/sec",
            "range": "stddev: 0.000025363327052307292",
            "extra": "mean: 368.21948266202764 usec\nrounds: 2855"
          },
          {
            "name": "tests/test_benchmarks.py::TestLocalSearchBenchmark::test_local_search_500",
            "value": 5480.150558148907,
            "unit": "iter/sec",
            "range": "stddev: 0.000010613134363129502",
            "extra": "mean: 182.47673843796386 usec\nrounds: 5838"
          },
          {
            "name": "tests/test_benchmarks.py::TestWorkflowParseBenchmark::test_parse_20_step_workflow",
            "value": 22751.90886758743,
            "unit": "iter/sec",
            "range": "stddev: 0.000007117397352924748",
            "extra": "mean: 43.952356077894144 usec\nrounds: 25149"
          },
          {
            "name": "tests/test_benchmarks.py::TestYAMLLoadBenchmark::test_load_yaml_10_steps",
            "value": 516.184379682857,
            "unit": "iter/sec",
            "range": "stddev: 0.00010212916887903929",
            "extra": "mean: 1.937292253234007 msec\nrounds: 541"
          },
          {
            "name": "tests/test_benchmarks.py::TestConditionEvalBenchmark::test_condition_evaluate_1000",
            "value": 7157.278000656285,
            "unit": "iter/sec",
            "range": "stddev: 0.00001913306446801657",
            "extra": "mean: 139.7179206827379 usec\nrounds: 7968"
          },
          {
            "name": "tests/test_benchmarks.py::TestCacheBenchmark::test_cache_set_get_1000",
            "value": 57.82353188468407,
            "unit": "iter/sec",
            "range": "stddev: 0.0011847557695650757",
            "extra": "mean: 17.293997225805462 msec\nrounds: 62"
          },
          {
            "name": "tests/test_benchmarks.py::TestTaskStoreBenchmark::test_record_query_100",
            "value": 10.161560186576406,
            "unit": "iter/sec",
            "range": "stddev: 0.012768494841269209",
            "extra": "mean: 98.41008483333269 msec\nrounds: 12"
          },
          {
            "name": "tests/test_benchmarks.py::TestBudgetBenchmark::test_budget_record_usage_500",
            "value": 766.8854327317059,
            "unit": "iter/sec",
            "range": "stddev: 0.00010659988939536355",
            "extra": "mean: 1.3039757404674146 msec\nrounds: 813"
          },
          {
            "name": "tests/test_benchmarks.py::TestCheckpointBenchmark::test_checkpoint_lifecycle_20",
            "value": 47.0138529538214,
            "unit": "iter/sec",
            "range": "stddev: 0.005901373316133427",
            "extra": "mean: 21.27032644999834 msec\nrounds: 60"
          },
          {
            "name": "tests/test_benchmarks.py::TestSkillLookupBenchmark::test_skill_lookup_100",
            "value": 13509.185488286716,
            "unit": "iter/sec",
            "range": "stddev: 0.000006055766573404004",
            "extra": "mean: 74.02370785914967 usec\nrounds: 15027"
          },
          {
            "name": "tests/test_benchmarks.py::TestSessionControllerBenchmark::test_policy_check_latency",
            "value": 1934543.8382029529,
            "unit": "iter/sec",
            "range": "stddev: 1.1129609520811155e-7",
            "extra": "mean: 516.9177251257978 nsec\nrounds: 188289"
          },
          {
            "name": "tests/test_benchmarks.py::TestSessionControllerBenchmark::test_event_log_throughput",
            "value": 8600.781654071094,
            "unit": "iter/sec",
            "range": "stddev: 0.000011600970201210587",
            "extra": "mean: 116.2685021223228 usec\nrounds: 9424"
          },
          {
            "name": "tests/test_benchmarks.py::TestCheckpointBenchmark::test_checkpoint_save_latency",
            "value": 1100.661237040881,
            "unit": "iter/sec",
            "range": "stddev: 0.0003397791752925834",
            "extra": "mean: 908.5447605009623 usec\nrounds: 1357"
          },
          {
            "name": "tests/test_benchmarks.py::TestCheckpointBenchmark::test_checkpoint_load_latency",
            "value": 11299.150593416127,
            "unit": "iter/sec",
            "range": "stddev: 0.000008330490819724287",
            "extra": "mean: 88.5022278207963 usec\nrounds: 13515"
          },
          {
            "name": "tests/test_benchmarks.py::TestCheckpointBenchmark::test_checkpoint_list_recent",
            "value": 9450.555991907597,
            "unit": "iter/sec",
            "range": "stddev: 0.00000901604390847839",
            "extra": "mean: 105.81388024749958 usec\nrounds: 10672"
          },
          {
            "name": "tests/test_benchmarks.py::TestContextManagerBenchmark::test_finalize_summary_latency",
            "value": 344388.90010508464,
            "unit": "iter/sec",
            "range": "stddev: 5.25609828197892e-7",
            "extra": "mean: 2.9036940496481343 usec\nrounds: 187653"
          },
          {
            "name": "tests/test_benchmarks.py::TestResolverBenchmark::test_resolve_50_intents",
            "value": 959.886196202913,
            "unit": "iter/sec",
            "range": "stddev: 0.00004861395946625708",
            "extra": "mean: 1.041790166329892 msec\nrounds: 992"
          },
          {
            "name": "tests/test_benchmarks.py::TestStructuralOverlapBenchmark::test_structural_overlaps_1000",
            "value": 397.87547073459234,
            "unit": "iter/sec",
            "range": "stddev: 0.00009048245809735384",
            "extra": "mean: 2.5133492098764294 msec\nrounds: 405"
          },
          {
            "name": "tests/test_benchmarks.py::TestConstraintBenchmark::test_validate_20_constraints",
            "value": 239906.28110653165,
            "unit": "iter/sec",
            "range": "stddev: 6.379008185859153e-7",
            "extra": "mean: 4.168294366398622 usec\nrounds: 127698"
          },
          {
            "name": "tests/test_benchmarks.py::TestPhiScoringBenchmark::test_phi_score_100_outcomes",
            "value": 126148.8612129965,
            "unit": "iter/sec",
            "range": "stddev: 9.569077851552093e-7",
            "extra": "mean: 7.927142507545482 usec\nrounds: 138947"
          },
          {
            "name": "tests/test_benchmarks.py::TestRealisticScenarioBenchmark::test_realistic_25_agents",
            "value": 271.6781743281828,
            "unit": "iter/sec",
            "range": "stddev: 0.00021338409021735212",
            "extra": "mean: 3.680825677192663 msec\nrounds: 285"
          },
          {
            "name": "tests/test_benchmarks.py::TestPublishThroughputBenchmark::test_publish_100_intents",
            "value": 1334.0844628479294,
            "unit": "iter/sec",
            "range": "stddev: 0.000036331321233278464",
            "extra": "mean: 749.577727534024 usec\nrounds: 1391"
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
          "id": "a68c2422a783b87bd7eaecb477a8f2ef18f7f7c3",
          "message": "Add operator-approved knowledge edge promotion (#159)\n\n* Require unverified status for scoped knowledge edge writes\n\n* Bind knowledge edge promotion to operator approval\n\n* Add interactive operator review for knowledge edge promotion\n\n* Use the terminal login for edge approval attribution",
          "timestamp": "2026-11-23T14:51:14-08:00",
          "tree_id": "8bfb843434c4fb088f576b4814d50b191c9b8b14",
          "url": "https://github.com/Arete-Consortium/animus/commit/a68c2422a783b87bd7eaecb477a8f2ef18f7f7c3"
        },
        "date": 1795475346983,
        "tool": "pytest",
        "benches": [
          {
            "name": "tests/test_benchmarks.py::TestMemorySerdeBenchmark::test_memory_serde_500",
            "value": 327.1008458242814,
            "unit": "iter/sec",
            "range": "stddev: 0.00005770359491909752",
            "extra": "mean: 3.0571611561567167 msec\nrounds: 333"
          },
          {
            "name": "tests/test_benchmarks.py::TestConversationSerdeBenchmark::test_conversation_serde_50msg",
            "value": 731.4475278861174,
            "unit": "iter/sec",
            "range": "stddev: 0.00002505249126392838",
            "extra": "mean: 1.3671520674763902 msec\nrounds: 741"
          },
          {
            "name": "tests/test_benchmarks.py::TestDetectModeBenchmark::test_detect_mode_1000",
            "value": 249.66746701604072,
            "unit": "iter/sec",
            "range": "stddev: 0.0000556035820785002",
            "extra": "mean: 4.005327614173102 msec\nrounds: 254"
          },
          {
            "name": "tests/test_benchmarks.py::TestEntitySearchBenchmark::test_entity_search_200",
            "value": 2165.8559861490135,
            "unit": "iter/sec",
            "range": "stddev: 0.00001972810497871705",
            "extra": "mean: 461.71121551717 usec\nrounds: 2204"
          },
          {
            "name": "tests/test_benchmarks.py::TestLocalSearchBenchmark::test_local_search_500",
            "value": 4128.0776894742385,
            "unit": "iter/sec",
            "range": "stddev: 0.000010208782108256876",
            "extra": "mean: 242.24350296260104 usec\nrounds: 4219"
          },
          {
            "name": "tests/test_benchmarks.py::TestWorkflowParseBenchmark::test_parse_20_step_workflow",
            "value": 19379.186136434164,
            "unit": "iter/sec",
            "range": "stddev: 0.000002597992101907855",
            "extra": "mean: 51.6017542202112 usec\nrounds: 19904"
          },
          {
            "name": "tests/test_benchmarks.py::TestYAMLLoadBenchmark::test_load_yaml_10_steps",
            "value": 404.33433357521466,
            "unit": "iter/sec",
            "range": "stddev: 0.00002735011544453764",
            "extra": "mean: 2.4732008067625033 msec\nrounds: 414"
          },
          {
            "name": "tests/test_benchmarks.py::TestConditionEvalBenchmark::test_condition_evaluate_1000",
            "value": 5673.769567612398,
            "unit": "iter/sec",
            "range": "stddev: 0.00000959411025638811",
            "extra": "mean: 176.2496675417176 usec\nrounds: 5712"
          },
          {
            "name": "tests/test_benchmarks.py::TestCacheBenchmark::test_cache_set_get_1000",
            "value": 44.653009635565475,
            "unit": "iter/sec",
            "range": "stddev: 0.00021829832803594085",
            "extra": "mean: 22.394907043477637 msec\nrounds: 46"
          },
          {
            "name": "tests/test_benchmarks.py::TestTaskStoreBenchmark::test_record_query_100",
            "value": 16.62193654292599,
            "unit": "iter/sec",
            "range": "stddev: 0.003362947552672967",
            "extra": "mean: 60.16146177778441 msec\nrounds: 18"
          },
          {
            "name": "tests/test_benchmarks.py::TestBudgetBenchmark::test_budget_record_usage_500",
            "value": 595.5784778456464,
            "unit": "iter/sec",
            "range": "stddev: 0.0001376250273702467",
            "extra": "mean: 1.6790398531814743 msec\nrounds: 613"
          },
          {
            "name": "tests/test_benchmarks.py::TestCheckpointBenchmark::test_checkpoint_lifecycle_20",
            "value": 72.8818663538978,
            "unit": "iter/sec",
            "range": "stddev: 0.0014194484905220254",
            "extra": "mean: 13.720834139238791 msec\nrounds: 79"
          },
          {
            "name": "tests/test_benchmarks.py::TestSkillLookupBenchmark::test_skill_lookup_100",
            "value": 10553.363670076918,
            "unit": "iter/sec",
            "range": "stddev: 0.000005329548558201599",
            "extra": "mean: 94.75651851507847 usec\nrounds: 11018"
          },
          {
            "name": "tests/test_benchmarks.py::TestSessionControllerBenchmark::test_policy_check_latency",
            "value": 1465542.742822593,
            "unit": "iter/sec",
            "range": "stddev: 6.690882894310463e-8",
            "extra": "mean: 682.3410677699026 nsec\nrounds: 153422"
          },
          {
            "name": "tests/test_benchmarks.py::TestSessionControllerBenchmark::test_event_log_throughput",
            "value": 6915.305203425516,
            "unit": "iter/sec",
            "range": "stddev: 0.00000642115717018015",
            "extra": "mean: 144.6067773703823 usec\nrounds: 7362"
          },
          {
            "name": "tests/test_benchmarks.py::TestCheckpointBenchmark::test_checkpoint_save_latency",
            "value": 1675.636784309684,
            "unit": "iter/sec",
            "range": "stddev: 0.00007294164210756095",
            "extra": "mean: 596.7880446190924 usec\nrounds: 1905"
          },
          {
            "name": "tests/test_benchmarks.py::TestCheckpointBenchmark::test_checkpoint_load_latency",
            "value": 8499.053862080682,
            "unit": "iter/sec",
            "range": "stddev: 0.000007932144147002036",
            "extra": "mean: 117.66015561586129 usec\nrounds: 9215"
          },
          {
            "name": "tests/test_benchmarks.py::TestCheckpointBenchmark::test_checkpoint_list_recent",
            "value": 6978.974201207552,
            "unit": "iter/sec",
            "range": "stddev: 0.0000075849572826781744",
            "extra": "mean: 143.287533549984 usec\nrounds: 7392"
          },
          {
            "name": "tests/test_benchmarks.py::TestContextManagerBenchmark::test_finalize_summary_latency",
            "value": 274126.6514395769,
            "unit": "iter/sec",
            "range": "stddev: 3.2312166827313796e-7",
            "extra": "mean: 3.6479488395181465 usec\nrounds: 143431"
          },
          {
            "name": "tests/test_benchmarks.py::TestResolverBenchmark::test_resolve_50_intents",
            "value": 756.6976557628948,
            "unit": "iter/sec",
            "range": "stddev: 0.0000432362866176821",
            "extra": "mean: 1.3215317800764301 msec\nrounds: 773"
          },
          {
            "name": "tests/test_benchmarks.py::TestStructuralOverlapBenchmark::test_structural_overlaps_1000",
            "value": 307.86409029129123,
            "unit": "iter/sec",
            "range": "stddev: 0.00007191479758614515",
            "extra": "mean: 3.248186558730613 msec\nrounds: 315"
          },
          {
            "name": "tests/test_benchmarks.py::TestConstraintBenchmark::test_validate_20_constraints",
            "value": 203987.94015355725,
            "unit": "iter/sec",
            "range": "stddev: 4.387248949507885e-7",
            "extra": "mean: 4.9022505901438285 usec\nrounds: 106758"
          },
          {
            "name": "tests/test_benchmarks.py::TestPhiScoringBenchmark::test_phi_score_100_outcomes",
            "value": 115627.11992786618,
            "unit": "iter/sec",
            "range": "stddev: 7.226351480652424e-7",
            "extra": "mean: 8.648490082809714 usec\nrounds: 118078"
          },
          {
            "name": "tests/test_benchmarks.py::TestRealisticScenarioBenchmark::test_realistic_25_agents",
            "value": 225.41517867804885,
            "unit": "iter/sec",
            "range": "stddev: 0.000378580751863815",
            "extra": "mean: 4.43625848917769 msec\nrounds: 231"
          },
          {
            "name": "tests/test_benchmarks.py::TestPublishThroughputBenchmark::test_publish_100_intents",
            "value": 1033.0738059498565,
            "unit": "iter/sec",
            "range": "stddev: 0.000009627633968725997",
            "extra": "mean: 967.9850502845275 usec\nrounds: 1054"
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
          "id": "7b0da4fdce1fec97fd37ace381ee72dc0b34617a",
          "message": "Add PostgreSQL registry backup and restore commands (#161)\n\n* Add PostgreSQL registry backup and restore commands\n\n* Exercise the registry backup round-trip in PostgreSQL CI\n\n* Pin database CI to a runner with PostgreSQL 16 clients",
          "timestamp": "2026-11-23T17:10:40-08:00",
          "tree_id": "dcaee3df1f15a7380bedc1c7606ad5a43ee1b0ac",
          "url": "https://github.com/Arete-Consortium/animus/commit/7b0da4fdce1fec97fd37ace381ee72dc0b34617a"
        },
        "date": 1795483679954,
        "tool": "pytest",
        "benches": [
          {
            "name": "tests/test_benchmarks.py::TestMemorySerdeBenchmark::test_memory_serde_500",
            "value": 540.0740550131429,
            "unit": "iter/sec",
            "range": "stddev: 0.000018344678798622084",
            "extra": "mean: 1.8515979257245836 msec\nrounds: 552"
          },
          {
            "name": "tests/test_benchmarks.py::TestConversationSerdeBenchmark::test_conversation_serde_50msg",
            "value": 1253.9531473477475,
            "unit": "iter/sec",
            "range": "stddev: 0.000011145080006637094",
            "extra": "mean: 797.4779616886906 usec\nrounds: 1279"
          },
          {
            "name": "tests/test_benchmarks.py::TestDetectModeBenchmark::test_detect_mode_1000",
            "value": 410.11962120289814,
            "unit": "iter/sec",
            "range": "stddev: 0.00004473724717250649",
            "extra": "mean: 2.4383129904074274 msec\nrounds: 417"
          },
          {
            "name": "tests/test_benchmarks.py::TestEntitySearchBenchmark::test_entity_search_200",
            "value": 3910.9883956598715,
            "unit": "iter/sec",
            "range": "stddev: 0.000005876397095581547",
            "extra": "mean: 255.68984073430815 usec\nrounds: 4031"
          },
          {
            "name": "tests/test_benchmarks.py::TestLocalSearchBenchmark::test_local_search_500",
            "value": 7343.690731564476,
            "unit": "iter/sec",
            "range": "stddev: 0.000004278321873029882",
            "extra": "mean: 136.17131174952996 usec\nrounds: 7413"
          },
          {
            "name": "tests/test_benchmarks.py::TestWorkflowParseBenchmark::test_parse_20_step_workflow",
            "value": 30982.44573779638,
            "unit": "iter/sec",
            "range": "stddev: 0.0000016145835831960553",
            "extra": "mean: 32.27634152781138 usec\nrounds: 31769"
          },
          {
            "name": "tests/test_benchmarks.py::TestYAMLLoadBenchmark::test_load_yaml_10_steps",
            "value": 678.9052747451277,
            "unit": "iter/sec",
            "range": "stddev: 0.000056006759916781674",
            "extra": "mean: 1.472959538244001 msec\nrounds: 706"
          },
          {
            "name": "tests/test_benchmarks.py::TestConditionEvalBenchmark::test_condition_evaluate_1000",
            "value": 9859.588514014617,
            "unit": "iter/sec",
            "range": "stddev: 0.00000532281456359405",
            "extra": "mean: 101.42411101422539 usec\nrounds: 10314"
          },
          {
            "name": "tests/test_benchmarks.py::TestCacheBenchmark::test_cache_set_get_1000",
            "value": 67.69069735702516,
            "unit": "iter/sec",
            "range": "stddev: 0.0003954083564878138",
            "extra": "mean: 14.773078710145933 msec\nrounds: 69"
          },
          {
            "name": "tests/test_benchmarks.py::TestTaskStoreBenchmark::test_record_query_100",
            "value": 11.624383355814748,
            "unit": "iter/sec",
            "range": "stddev: 0.014473770023831186",
            "extra": "mean: 86.02606859999848 msec\nrounds: 15"
          },
          {
            "name": "tests/test_benchmarks.py::TestBudgetBenchmark::test_budget_record_usage_500",
            "value": 934.2907624373538,
            "unit": "iter/sec",
            "range": "stddev: 0.00015452877274353273",
            "extra": "mean: 1.0703306082051218 msec\nrounds: 975"
          },
          {
            "name": "tests/test_benchmarks.py::TestCheckpointBenchmark::test_checkpoint_lifecycle_20",
            "value": 46.39041489324244,
            "unit": "iter/sec",
            "range": "stddev: 0.007029437253697308",
            "extra": "mean: 21.556177117649945 msec\nrounds: 68"
          },
          {
            "name": "tests/test_benchmarks.py::TestSkillLookupBenchmark::test_skill_lookup_100",
            "value": 19387.123011526026,
            "unit": "iter/sec",
            "range": "stddev: 0.0000018424068419810694",
            "extra": "mean: 51.580629029148895 usec\nrounds: 19918"
          },
          {
            "name": "tests/test_benchmarks.py::TestSessionControllerBenchmark::test_policy_check_latency",
            "value": 2808820.8933677576,
            "unit": "iter/sec",
            "range": "stddev: 4.842359258049437e-8",
            "extra": "mean: 356.021276529671 nsec\nrounds: 189108"
          },
          {
            "name": "tests/test_benchmarks.py::TestSessionControllerBenchmark::test_event_log_throughput",
            "value": 10122.408002862183,
            "unit": "iter/sec",
            "range": "stddev: 0.000005135879778572897",
            "extra": "mean: 98.79072249579772 usec\nrounds: 10771"
          },
          {
            "name": "tests/test_benchmarks.py::TestCheckpointBenchmark::test_checkpoint_save_latency",
            "value": 1321.8825105782425,
            "unit": "iter/sec",
            "range": "stddev: 0.00025454178992392814",
            "extra": "mean: 756.4968837983652 usec\nrounds: 1506"
          },
          {
            "name": "tests/test_benchmarks.py::TestCheckpointBenchmark::test_checkpoint_load_latency",
            "value": 12461.275799718758,
            "unit": "iter/sec",
            "range": "stddev: 0.000006403420450065898",
            "extra": "mean: 80.24860504432213 usec\nrounds: 14194"
          },
          {
            "name": "tests/test_benchmarks.py::TestCheckpointBenchmark::test_checkpoint_list_recent",
            "value": 10305.904740005084,
            "unit": "iter/sec",
            "range": "stddev: 0.00000574827502945718",
            "extra": "mean: 97.03175269205009 usec\nrounds: 11237"
          },
          {
            "name": "tests/test_benchmarks.py::TestContextManagerBenchmark::test_finalize_summary_latency",
            "value": 529320.4459748823,
            "unit": "iter/sec",
            "range": "stddev: 1.4365956751359805e-7",
            "extra": "mean: 1.8892147613120025 usec\nrounds: 53857"
          },
          {
            "name": "tests/test_benchmarks.py::TestResolverBenchmark::test_resolve_50_intents",
            "value": 1261.8812535549382,
            "unit": "iter/sec",
            "range": "stddev: 0.000013678833910604358",
            "extra": "mean: 792.4675932722091 usec\nrounds: 1308"
          },
          {
            "name": "tests/test_benchmarks.py::TestStructuralOverlapBenchmark::test_structural_overlaps_1000",
            "value": 496.31099748519745,
            "unit": "iter/sec",
            "range": "stddev: 0.00004501629871711474",
            "extra": "mean: 2.014865689188814 msec\nrounds: 518"
          },
          {
            "name": "tests/test_benchmarks.py::TestConstraintBenchmark::test_validate_20_constraints",
            "value": 349132.30274273537,
            "unit": "iter/sec",
            "range": "stddev: 2.7689247577040205e-7",
            "extra": "mean: 2.8642437040174666 usec\nrounds: 181226"
          },
          {
            "name": "tests/test_benchmarks.py::TestPhiScoringBenchmark::test_phi_score_100_outcomes",
            "value": 175071.5517186578,
            "unit": "iter/sec",
            "range": "stddev: 5.790694562198966e-7",
            "extra": "mean: 5.711950286514925 usec\nrounds: 178000"
          },
          {
            "name": "tests/test_benchmarks.py::TestRealisticScenarioBenchmark::test_realistic_25_agents",
            "value": 381.3379778778541,
            "unit": "iter/sec",
            "range": "stddev: 0.000034544600485166284",
            "extra": "mean: 2.622345682863795 msec\nrounds: 391"
          },
          {
            "name": "tests/test_benchmarks.py::TestPublishThroughputBenchmark::test_publish_100_intents",
            "value": 1715.9337894146493,
            "unit": "iter/sec",
            "range": "stddev: 0.000011462187320349534",
            "extra": "mean: 582.7730686165501 usec\nrounds: 1778"
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
          "id": "8d1155b4408b4d94d523c8bb7275748a4807db14",
          "message": "Provide scoped knowledge edge snapshots to Forgehand (#162)",
          "timestamp": "2026-11-23T17:30:58-08:00",
          "tree_id": "d799a67d26b6dd51ad13d17a34251b6677c2490a",
          "url": "https://github.com/Arete-Consortium/animus/commit/8d1155b4408b4d94d523c8bb7275748a4807db14"
        },
        "date": 1795484953661,
        "tool": "pytest",
        "benches": [
          {
            "name": "tests/test_benchmarks.py::TestMemorySerdeBenchmark::test_memory_serde_500",
            "value": 459.05240488580273,
            "unit": "iter/sec",
            "range": "stddev: 0.00003784766522515594",
            "extra": "mean: 2.178400525423165 msec\nrounds: 472"
          },
          {
            "name": "tests/test_benchmarks.py::TestConversationSerdeBenchmark::test_conversation_serde_50msg",
            "value": 1074.8161872770904,
            "unit": "iter/sec",
            "range": "stddev: 0.000012863762748942549",
            "extra": "mean: 930.3916444851583 usec\nrounds: 1097"
          },
          {
            "name": "tests/test_benchmarks.py::TestDetectModeBenchmark::test_detect_mode_1000",
            "value": 357.01630708568047,
            "unit": "iter/sec",
            "range": "stddev: 0.0000217100235662552",
            "extra": "mean: 2.8009925041323385 msec\nrounds: 363"
          },
          {
            "name": "tests/test_benchmarks.py::TestEntitySearchBenchmark::test_entity_search_200",
            "value": 3159.759993259165,
            "unit": "iter/sec",
            "range": "stddev: 0.000010161771688510518",
            "extra": "mean: 316.47973331308003 usec\nrounds: 3266"
          },
          {
            "name": "tests/test_benchmarks.py::TestLocalSearchBenchmark::test_local_search_500",
            "value": 5695.527900232252,
            "unit": "iter/sec",
            "range": "stddev: 0.000009906825459468868",
            "extra": "mean: 175.57634999193348 usec\nrounds: 6303"
          },
          {
            "name": "tests/test_benchmarks.py::TestWorkflowParseBenchmark::test_parse_20_step_workflow",
            "value": 26954.062876993463,
            "unit": "iter/sec",
            "range": "stddev: 0.000005308331654485756",
            "extra": "mean: 37.100158316153006 usec\nrounds: 29340"
          },
          {
            "name": "tests/test_benchmarks.py::TestYAMLLoadBenchmark::test_load_yaml_10_steps",
            "value": 597.2095226060111,
            "unit": "iter/sec",
            "range": "stddev: 0.000017045217520294156",
            "extra": "mean: 1.6744542110386214 msec\nrounds: 616"
          },
          {
            "name": "tests/test_benchmarks.py::TestConditionEvalBenchmark::test_condition_evaluate_1000",
            "value": 8167.246129233872,
            "unit": "iter/sec",
            "range": "stddev: 0.000011354025630917727",
            "extra": "mean: 122.44029188989371 usec\nrounds: 8767"
          },
          {
            "name": "tests/test_benchmarks.py::TestCacheBenchmark::test_cache_set_get_1000",
            "value": 64.64214380491983,
            "unit": "iter/sec",
            "range": "stddev: 0.000054473655109996556",
            "extra": "mean: 15.469783969693953 msec\nrounds: 66"
          },
          {
            "name": "tests/test_benchmarks.py::TestTaskStoreBenchmark::test_record_query_100",
            "value": 28.850884265673727,
            "unit": "iter/sec",
            "range": "stddev: 0.001139956430305442",
            "extra": "mean: 34.66098268571208 msec\nrounds: 35"
          },
          {
            "name": "tests/test_benchmarks.py::TestBudgetBenchmark::test_budget_record_usage_500",
            "value": 914.8700119613582,
            "unit": "iter/sec",
            "range": "stddev: 0.00008454727842936159",
            "extra": "mean: 1.0930514575028365 msec\nrounds: 953"
          },
          {
            "name": "tests/test_benchmarks.py::TestCheckpointBenchmark::test_checkpoint_lifecycle_20",
            "value": 136.71363950240834,
            "unit": "iter/sec",
            "range": "stddev: 0.000387245812930468",
            "extra": "mean: 7.314559129869292 msec\nrounds: 154"
          },
          {
            "name": "tests/test_benchmarks.py::TestSkillLookupBenchmark::test_skill_lookup_100",
            "value": 15795.206130964127,
            "unit": "iter/sec",
            "range": "stddev: 0.000002905654551664868",
            "extra": "mean: 63.310348197333774 usec\nrounds: 16864"
          },
          {
            "name": "tests/test_benchmarks.py::TestSessionControllerBenchmark::test_policy_check_latency",
            "value": 2251119.639504994,
            "unit": "iter/sec",
            "range": "stddev: 7.151915192085773e-8",
            "extra": "mean: 444.223391085466 nsec\nrounds: 198887"
          },
          {
            "name": "tests/test_benchmarks.py::TestSessionControllerBenchmark::test_event_log_throughput",
            "value": 9989.592107750932,
            "unit": "iter/sec",
            "range": "stddev: 0.00003302231116018523",
            "extra": "mean: 100.1041873595719 usec\nrounds: 10696"
          },
          {
            "name": "tests/test_benchmarks.py::TestCheckpointBenchmark::test_checkpoint_save_latency",
            "value": 2059.0269951983623,
            "unit": "iter/sec",
            "range": "stddev: 0.00019809625873345278",
            "extra": "mean: 485.6662891414215 usec\nrounds: 3168"
          },
          {
            "name": "tests/test_benchmarks.py::TestCheckpointBenchmark::test_checkpoint_load_latency",
            "value": 13716.055560940893,
            "unit": "iter/sec",
            "range": "stddev: 0.000006973932152865378",
            "extra": "mean: 72.90725788890009 usec\nrounds: 15433"
          },
          {
            "name": "tests/test_benchmarks.py::TestCheckpointBenchmark::test_checkpoint_list_recent",
            "value": 11283.705385816545,
            "unit": "iter/sec",
            "range": "stddev: 0.000006283441893023014",
            "extra": "mean: 88.62337023235165 usec\nrounds: 12349"
          },
          {
            "name": "tests/test_benchmarks.py::TestContextManagerBenchmark::test_finalize_summary_latency",
            "value": 408833.2341133363,
            "unit": "iter/sec",
            "range": "stddev: 1.9613132537411173e-7",
            "extra": "mean: 2.4459851023823105 usec\nrounds: 42537"
          },
          {
            "name": "tests/test_benchmarks.py::TestResolverBenchmark::test_resolve_50_intents",
            "value": 1115.038428693106,
            "unit": "iter/sec",
            "range": "stddev: 0.000017597877487594326",
            "extra": "mean: 896.8300771230475 usec\nrounds: 1154"
          },
          {
            "name": "tests/test_benchmarks.py::TestStructuralOverlapBenchmark::test_structural_overlaps_1000",
            "value": 457.23003203710755,
            "unit": "iter/sec",
            "range": "stddev: 0.00003785238423053523",
            "extra": "mean: 2.187082934042361 msec\nrounds: 470"
          },
          {
            "name": "tests/test_benchmarks.py::TestConstraintBenchmark::test_validate_20_constraints",
            "value": 288660.4760734084,
            "unit": "iter/sec",
            "range": "stddev: 4.362492923134525e-7",
            "extra": "mean: 3.464277526327134 usec\nrounds: 151355"
          },
          {
            "name": "tests/test_benchmarks.py::TestPhiScoringBenchmark::test_phi_score_100_outcomes",
            "value": 147473.21748808902,
            "unit": "iter/sec",
            "range": "stddev: 8.197141628144488e-7",
            "extra": "mean: 6.780892266629817 usec\nrounds: 152766"
          },
          {
            "name": "tests/test_benchmarks.py::TestRealisticScenarioBenchmark::test_realistic_25_agents",
            "value": 322.1072782235326,
            "unit": "iter/sec",
            "range": "stddev: 0.000021523697684932648",
            "extra": "mean: 3.1045557415378564 msec\nrounds: 325"
          },
          {
            "name": "tests/test_benchmarks.py::TestPublishThroughputBenchmark::test_publish_100_intents",
            "value": 1520.6295182428357,
            "unit": "iter/sec",
            "range": "stddev: 0.00001120380932498274",
            "extra": "mean: 657.622378102689 usec\nrounds: 1571"
          }
        ]
      }
    ]
  }
}