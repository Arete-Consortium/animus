window.BENCHMARK_DATA = {
  "lastUpdate": 1792295663687,
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
      }
    ]
  }
}