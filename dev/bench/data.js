window.BENCHMARK_DATA = {
  "lastUpdate": 1794982408318,
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
      }
    ]
  }
}