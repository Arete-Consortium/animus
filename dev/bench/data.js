window.BENCHMARK_DATA = {
  "lastUpdate": 1794814915702,
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
      }
    ]
  }
}