# ML inference progress ledger

## Integration checkpoint: 2026-11-14 18:34 UTC

- Current worktree is fast-forwarded onto main `9843157012595ab03cb3e7683bb8a6c731ace489`; original tracked ML changes preserved in stash `84afde87f335c50de98ac6b090a1bab4afc9eb55`. All conflicts resolved by preserving upstream metadata/equipment/deep/shared cache and mobile frontend, plus analysis additions. Stash is retained until committed integration is verified.
- `Api.make` and `GrpcServer.start` append analyses last and Main uses named arguments. Input snapshots use `ZIO.scoped` with `Jobs.leasedResource` through independent hardlink/copy creation; upstream scoped download routes remain intact. Final lease-aware `./sbtw test stage` passed 119 tests, zero failures; log `/tmp/spaceapps-ml-integration-test-stage.log`.
- Runtime model is frozen v2 `dde04fc3996be19150c57ca0399a7de52d6e7b62b2b65731133159585a3580a9`. An interrupted release promotion was completed without changing weights/source: repaired empty subgroup report, retained compressed complete final synthetic fields and repaired 27-artifact inventory. Full scientific suite passed 78 tests and real-data CLI smoke verified v2; logs `/tmp/spaceapps-v2-release-pytest.log` and `/tmp/spaceapps-v2-release-smoke.log`.
- Merged OpenAPI has 20 paths, no duplicate keys and all local references resolve. Frontend lint/build passed (five preexisting warnings); new ML navigation is available in desktop and mobile menus.
- Other thread's per-image Processor commit `b39d8db` is still outside main, with no PR visible. Do not import its unreviewed worktree changes. ML uses native inputs and owns its own preparation/evidence; its delivery does not require that separate per-image endpoint work. Cross-thread connector currently fails with a transport error; no message delivery claimed.
- Fresh SSH read confirms production backend and frontend still run healthy main `9843157`; no ML deployed. Fresh local Vite session 91213 is on port18087, proxy18086. Earlier local API and temporary handles are gone; start a fresh staged API before runtime checks. Docker application operations on VPS require `sudo -n docker`.
- Remaining: actual integrated HTTP/gRPC/native retrieval/browser checks, final independent review, commit/PR/CI/container/rollback, merge/deploy and deployed completion audit. Goal stays active.

## Current checkpoint: 2026-11-14 16:40 UTC

### Final v2 evidence at 16:43 UTC

- V2 was frozen before the reserved field was opened. SHA-256 `dde04fc3996be19150c57ca0399a7de52d6e7b62b2b65731133159585a3580a9`; original freeze 16:39:45 UTC, accounting-only evaluator amendment 16:41:55 UTC. Original evaluator is archived, two accounting regression tests reproduced failures then all eight background-evaluation tests passed. See `ML-MODEL-V2-PRETEST-ACCOUNTING.AI.md`.
- Root's independent real-field run (session 11619, terminal exit 0; `/tmp/spaceapps-v2-final-real.log`) completed in 4.39 seconds. One independent DR1 D1 parent field/four exposures, 150 correlated injection trials, all with at least three finite-center epochs. Detector recovered 28/150; model retained 24 at top three versus heuristic 17, but only 11 at top one versus heuristic 15. Three unmodified control tracks remain UNKNOWN; no ambiguous preexisting injection matches and no peak caps. Report both review budgets and low detector completeness. No model retuning on this field is authorized by this evaluation.
- Reserved synthetic 400 independent fields/785 injected objects: 213 detected; model top one 81 versus heuristic 57, top three 143 versus 99. Paired whole-field bootstrap recall differences: top one +1.31..4.86 percentage points, top three +3.67..7.67 points. These synthetic numbers do not establish real survey precision.
- Model worker is promoting this already selected frozen v2 artifact and complete provenance/reports to the experimental runtime release. Root will checkpoint and merge current main (`7f3f288`) after its files stabilize. Full integrated tests, actual API/UI and production deployment still pending; goal remains active.

- The expanded v2 training process is terminal with exit 0 (worker session 27814; `/tmp/spherex-v2-candidate.log`), rather than still running. Candidate artifact SHA-256 is `dde04fc3996be19150c57ca0399a7de52d6e7b62b2b65731133159585a3580a9` under `backend/inference/models/experiments/v2-candidate`. Training used 1,500 fields and validation 400; 50,983 training rows include 866 positives. Validation top-one recovery is 76 versus heuristic 41, top-three 132 versus 67, out of 791 injections/215 detections. These are synthetic validation results, not a real-data completion claim.
- M101 is development data: v2 top-one 52 versus heuristic 65, top-three both 67, with two zero scores. The model worker is completing one declared epoch-feature ablation before freezing a candidate. Runtime default is still archived v1; final real field remains quarantined and unopened by training.
- Source Scala tests most recently passed 63/63 after preview-only failure/native-mode fixes. The old staged API is stopped (fresh process inspection found no `spaceapps.bootstrap.Main`); stage must be refreshed after upstream integration.
- The actual temporary Docker/Python3.12/ONNX CLI and Scala-to-Python container runs passed with archived v1. They prove packaging only; no production ML deployment has occurred.
- Other thread's Processor work has no PR yet. Its Python worker has 31 tests plus two real-FITS smoke checks and Scala child supervision has five tests. It will change Docker context to the project root and install its own hash-locked processing dependencies into the shared `/opt/inference-venv`. Reconcile this after its files stabilize.
- Fresh WhatsApp read added a frontend verification-feed update; no new ML requirements. OpenAPI now explicitly restricts `download_id` to native default-mode inputs.

Goal: read WhatsApp and build the corresponding ML inference; user allocated15hours starting2026-11-14 15:23UTC (approximately until2026-11-15 06:23UTC). Goal remains active. Worktree /home/usatovpavel/.codex/worktrees/spaceapps-zio-backend, branchfeat/ml-inference, baseorigin/main ca63aa4145f5a539b157f8bd25c237c8cca56148. Main has since advanced; fetch/reconcile before PR without overwriting teammates.

## Evidence and decisions

- Read latest WhatsApp SpaceAppsChallenge group120363431123227483@g.us, includingPaul18:19local data->backend->ML->listofstars direction; sourceprocessing underbackend/.
- Existingmainml/ demo actually trainsRandomForest eachbenchmark, notserverinference. Ivan origin/ivan/spherex-motion-review2b6dc435b0f73a6f255e50ca795900acfd69cd33 contains matureFITSregistration,detector/linker and4realNPZs. Reusedwithattribution, originalml/unchanged.
- Scientificreview recommends native/spectral/PSFcaution and realdataevaluation. Chosenfirststage freezes teamtrackRF; learnedranking is experimental, neverplanetprobability orclaimeddiscovery. Nativevariance onlyvalidity/registration; empiricalresidualSNR notformalsignificance. Passbandvariation/PSFmatching remainwarnings. Nativeanalysis requiresone detector; callers selectdetector atretrieval, mixedinputsrejectratherthanmixspectra.

## Current implementation

- Pythoncoreworkerimplement_ml_core completednativeFITS->common-grid->detector/linker->ONNX->PNG/resultJSON,4realpresets andsafeCLI. Finalafterreview59pytesttests pass. PhysicalOBSIDdedupsproductversions;trustedarchiveproductrelease/version separatefromsoftwareVERSION;inputSHA256computed. NativeSIP/rotatedtranslatedWCSinjectiontestpasses.
- Scala implement_ml_api completed durableanalysisSQLite/singleworker,hardlinksnapshots,Pythonchildsupervision,budgetedoutputs,HTTP+typedAnalysisServicegrpc. Afterindependentreview fixes,60Scala tests+stagepass. Fixesphysicalsourceidentity,provenance,TANsizeandmodelID/hash/resultbounds. Currentstagecontainsfixes; localAPIprocess18086stilloldloadedclasses andMUSTrestartbeforefinalverification.
- Root added6OpenAPIanalysispaths(total16),schemas,Pythonhashlocked3.12requirements, runtimeDockerPython/ONNXpackagingandCIactualmodelsmoke. DockerimagehasNOTyetbeenbuilt/testedwithnewML; noPR/merge/deployyet.
- Root implemented frontendrealMLpage/?analysis=1,requestclient,realframes/trajectory/stacks/ranks/JSONexport andlive/previousdownloadinputs; existingmockviewerpreserved. Viteproxy/backend->localAPI. Lint/buildpasswith6preexistingwarnings. ActualFirefoxUIcomputed10tracks/4framesviaPOSTanalysisandloadedrealPNG,noJSerrors. Screenshot/tmp/spaceapps-ml-ui-proof.png. ChangedpageCSSownscrollforbodyoverflowhidden. Needreruntestsafterfinalmodel/server.

## Critical model finding: do not claim complete

- Frozenv1modelSHA030c1edf972b76b3cb8fadcb4adadcc386a36eab9f2cdbcb65527c277c581ab9 trained300/val100/test200simulatedfields:101/306detected; RF58top3 vsheuristic0; false_top3482vs540;AP.3846vs.00238. RealcometD6 RF1/10,D2RF2/2;VestaonlyBLOOMnonML. Theseareselecteddevelopmentcases,notindependentsurveygold.
- Independent4-frameM101realbackgroundnative-ePSFinjectionevaluationfoundSERIOUSdomainshift:150injections,67detected; both67top3 butheuristic65top1 versusRF0top1.52/67positivevectorsscore0. NativePSF/SNR rangesoutsideGaussiantrain positives; epochsnotsolecause. ThisfieldisnowDEVELOPMENTafterdiagnosis,neverreuseasfreshheldouttest.
- Modelworkertrain_ml_ranker is activelybuildingv2afterrootapprovedbroader3–8epochs/cadences,ePSFshapes,SNR3–150andclass-overlappingbrightness/noisancedistributions; fixed6featurecontract. Preservev1inmodels/archive/v1. Needfrozenv2beforeopeningNEWheldoutfield. RootgettinggenericpubliccalibrationPSFs; newindependentfieldquarantined/tmp/spaceapps-ml-heldout-field1 (metadataqueryinprogress, DONOTgiveworkerpixelsbeforefreeze). Mainmetadatafilecanchangev2modelid/hash;Scalafreezesandvalidatesperacceptedjob.

## Runtime/process handles and data

- LocalJavaAPIinitialsession60326,PORT18086/GRPC15056,DATA_DIR/tmp/spaceapps-ml-api-live,log/tmp/spaceapps-ml-api-live.log,ML_ROOTabsolute worktree/backend/inference,ML_PYTHON/home/usatovpavel/edu/UtilsAI/.venv/bin/python. RestartthisOWNprocessaftercurrentstage60tests. Stopbyverified/proc cwd+PORT18086 identity, do notkillotheragents'processes.
- LocalVitedevsession23217,127.0.0.1:18087,VITE_API_PROXY=http://127.0.0.1:18086. No needrestartexceptconfigchange.
- ActualHTTPmodelcase88572c22-0af1-4982-8387-25265d504b67 completedwithv1:4frames10tracks,PNGverified. /tmp/spaceapps-ml-api-comet-result.json.
- Native4M101D2inputs/tmp/spaceapps-inference-real-data;3IRSAcutouts4MB+onepublicS3native65MB,downloads.json/individualprovenance. NativeCLIruncompleted4frames1UNREVIEWEDcandidate, nofalseclaim. Trustedprovenancerequestrequest-provenance.json/output-provenance result verifiedbycoreworker. Allnewtestdataoutsidegit.
- GenericS3publiccalibrationlistingsession61322; newheldoutSIAmetadataquerysession47261. Re-pollthesespecifichandlesifneeded; don'trestartsolelyonobservationtimeout.
- OriginalbenchmarkCLIreproducedRF4/25vsheuristic1/25undernewsklearn; thatisoldprototype,supersededbyexplicitv1metrics.
- Toolchainshared /home/usatovpavel/edu/UtilsAI/.venv Python3.14.4,numpy2.5.3 scipy1.18.1 sklearn1.9.1 astropy8.0.2 photutils3.1.1 skl2onnx1.20 onnxruntime1.30 pytest9.2. Addedpackagesdocumentedinmultimedia-utilsskill. DeliveryDocker/CIusePython3.12+hashlockedrequirements, nothostsharedvenv.

## Outstanding work

1. Fixv1domainshiftusingv2andnewtrulyheldoutrealnativeePSFtest; retainnegativeevidenceandsplitdefinitions. Freezeartifactbeforetest, neverlabelunknownrealtracksnegative.
2. Restartlocalcurrentstagedserver; actualHTTP/gRPC/Swagger/realUItestwithnewmodel,knownpresets,empty/error/restart,actualretrieval->nativeanalysisflow.
3. VerifyDocker/CI/rollback+smalllatencyandmemorybudget; CI3.12dependencyportability. Mainadvancedto7700f...whenVPSinspected; fetch/reconcilelatestonlyafterworkersstableandcommitsthensafelymergerebase.
4. FinishrunnableCLI/API/grpcdocsandfullindependentreviewincludingrootfrontend/packaging/OpenAPI. ExistingPythonreviewandScalareviewfindingsallfixed,butneedrecheckchangesandnewv2.
5. PRauthorizedflow,merge/deploywhenverified,useralreadyrequesteddeploymentinthissession;no directmainpush. RealVPS35.159.162.202/backend80/frontend8080/privategrpc127.0.0.1:50051. OwnerSSHkey/home/usatovpavel/.ssh/hackathon-lightsail-frankfurt-20261114. AllAWSinfraactionsuseofficialAWSMCP,neverBashAWSCLI.
6. Finalcompletionauditmustproveend-to-endactualmodelandrealdataAPI/UI,evaluationhonesty,budgetsafeerrorsandCIgreen. DoNOTcompletegoalforprototypeorcheckswhilemodelharmfulunresolved.

WhatsAppsendconnectorcurrentlyfailsunknownuserserver'lid';donotclaimmessagesdelivered. AGENTSflowrequiresnotifybutnoexternalmessagesmadeforthisgoal. ReadWhatsAppfreshifrequirementschange;neverasksendpermissionredundantlywhenAGENTSexplicitlyauthorizesflow.


## Update 2026-11-14 16:20 UTC

- Public generic ePSF calibrations for all6detectors are ready at /tmp/spaceapps-ml-calibration-epsf with exact URLs/hashes. Modelworker prepared384spatiallyspread templates(~1.6MB). New D1 heldout field4files ready at /tmp/spaceapps-ml-heldout-field1 (127.69444,-39.17760,2025W18_1B_0162_1..4D1); pixels remain unopened by modelworker untilv2freeze. They are unrelatedtoM101/training.
- V2pilot featurecoverage improved butM101development top1still6/150vsheuristic65/150. Targeted featureablation showed anepochshortcut (dropcount55top1;dropcount+shape64) buthurtssyntheticAP. Worker insteadtestingnewcoherentnegative families/per-epochPSFchanges, retaining6featureAPI; nofinalfreeze/heldouttestyet. DoNOTclaimready.
- Allreviewfixescomplete: core59tests;Scala61tests+stageafteratomicrenamebudgetscanraceRED/GREEN. LocalAPIrestartedwithstage61 session38410,PORT18086/GRPC15056; Vite23217on18087. Checkhandlesbeforestage/restart.
- RootfrontendresumedGEToverwritenewjobraceREPRODUCEDRED thenGREEN withabortguards. Script/tmp/spaceapps-ml-resume-race.cjs. Addedpersistedsource/settingssummaryandnativecachedFITSlinks, labelcontrolsasnewinputs. Positive/empty/errorcasesPASS,noJSerrors. Frontbuild/lintlatest session31233pendingpoll.
- RuntimeDockerimage spaceapps-api:ml-review-20261114 BUILT onVPSandactualread-only/2CPU/2GiBPython3.12CLIsmokePASSEDwitharchivedv1artifactSHA030c1edf...581ab9. NonfatalORTread-onlytelemetrydeviceIDwarning; noprodfiles/containersreplaced. Remotecontext/tmp/spaceapps-ml-review-20261114; localbuildlog/tmp/spaceapps-ml-review-docker-build.log. Mustrebuild/testfinalv2andmergedupstreambeforedeploy.
- OpenAPI16paths/allrefs andactualnativeAnalysisResultschema independentvalidationPASS. Front/packagingreviewotherwiseclearafterracefix; finalv2/fullintegratedcontainerCIpending.

### Critical coordination / upstream merge

Otheruserthread01a1d8c1-8242-7c03-ad19-cdaff7ad7016 ownsPR6metadata/equipment/deep/sharedFitsCache (merged8b853239...,104tests) andnextfeat/python-processing forper-imageProcessorcleaning/PNG/spectra. Latestorigin/main13d580e... hasupstreamfrontchanges,pipeline/service.py(syntheticfallbackDO NOTcall),ml/service.py(classicalonly,no consumer),compose.services.yaml(optionalNOTdeployed). OtherthreadwilllandProcessorfirst; rootwillreconcileafterworkersstable. NoMLfileownershipoverlap.

Requiredmergeadaptations:
- PreserveMain Repository->FitsCache->CapacityArchiveSome(cache)->Jobs->MetadataService->EquipmentService;appendAnalysisRepository/Analyses. PreserveotherthreadProcessorreplacement.
- AppendanalysesLASTaftermetadata/equipmentinApi.make/GrpcServer.start; useNAMEDarguments. PreserveupstreamHandler.scopedHTTPandZStream.unwrapScopedgrpcFITSreaders.
- Analyses snapshots MUSTchangejobs.resource(...) to ZIO.scoped{jobs.leasedResource(c.id,false).flatMap(link/copy)}. Leaseuntilindependenthardlink/copyexists. Jobs.cachedImage(image:ArchiveImage):ZIO[Scope,Throwable,Option[Path]],leasedResource(chunkId,preview):ZIO[Scope,Throwable,Resource]. SharedFitsCacheincludesallanalysispathsindiskbytesbutonlyevictsmanagedraw/jobsFITS, so cleanupmandatory.
- KeepQuery.deepfield8and4newRetrievalRPCs,appendAnalysisService. PreserveGrpcMapping.document/deep-roundtrip.
- MergeourAppwrapper/newpage/navintoLATESTupstreamAppkeepingverification/livequerychanges. LegacyMLhasno consumers;nonewports/proxiesneeded. Existingcompose.yamlrollbackstillused;DONOTswitchtocompose.services.yaml.
- OtherthreadmayreuseourPython3.12venv/locks viaPROCESSING_PYTHONfallbackML_PYTHON=/opt/inference-venv/bin/python, childPYTHONPATH=/app/pipeline. Runtimeconstraintsbackend/inference/requirements-inference.in/txt;trainingseparate. Coordinateuniondeps/Docker/CIwhentheymerge. Theywon'teditAnalyses/ONNX;rootdoesn'tintegrateSienna scripts.
