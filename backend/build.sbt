ThisBuild / scalaVersion := "3.9.0"
name := "spaceapps-backend"
version := sys.env.getOrElse("APP_REVISION", "development")
val zioVersion = "2.1.27"
libraryDependencies ++= Seq(
  "dev.zio" %% "zio" % zioVersion,
  "dev.zio" %% "zio-streams" % zioVersion,
  "dev.zio" %% "zio-http" % "3.11.6",
  "dev.zio" %% "zio-json" % "1.1.2",
  "org.xerial" % "sqlite-jdbc" % "3.54.1.0",
  "org.yaml" % "snakeyaml" % "2.5",
  "dev.zio" %% "zio-test" % zioVersion % Test,
  "dev.zio" %% "zio-test-sbt" % zioVersion % Test
)
testFrameworks += new TestFramework("zio.test.sbt.ZTestFramework")
Test / fork := true
Test / javaOptions += "--enable-native-access=ALL-UNNAMED"
Compile / run / fork := true
Compile / run / javaOptions += "--enable-native-access=ALL-UNNAMED"
Compile / mainClass := Some("spaceapps.bootstrap.Main")
// Export a dependency-complete classpath directory without a fat-JAR plugin.
lazy val stage = taskKey[File]("Stage the application and dependency jars")
stage := {
  val output = target.value / "stage"
  IO.delete(output)
  IO.createDirectory(output / "lib")
  (Compile / fullClasspath).value.foreach { entry =>
    if (entry.data.isDirectory) IO.copyDirectory(entry.data, output / "classes")
    else IO.copyFile(entry.data, output / "lib" / entry.data.getName)
  }
  output
}

val grpcVersion = "1.84.2"
val scalaPbVersion = "0.11.21"
libraryDependencies ++= Seq(
  "com.thesamet.scalapb.zio-grpc" %% "zio-grpc-core" % "0.6.4",
  "com.thesamet.scalapb" %% "scalapb-runtime" % scalaPbVersion % "protobuf",
  "com.thesamet.scalapb" %% "scalapb-runtime-grpc" % scalaPbVersion,
  "io.grpc" % "grpc-netty-shaded" % grpcVersion
)
// Keep gRPC's modules on the runtime's release and avoid unshaded Netty alongside ZIO HTTP.
dependencyOverrides ++= Seq("grpc-api", "grpc-core", "grpc-context", "grpc-util", "grpc-stub", "grpc-protobuf", "grpc-protobuf-lite", "grpc-services")
  .map("io.grpc" % _ % grpcVersion)
dependencyOverrides ++= Seq("zio", "zio-streams", "zio-internal-macros", "zio-stacktracer")
  .map("dev.zio" %% _ % zioVersion)
Compile / PB.protocVersion := "3.25.8"
Compile / PB.targets := Seq(
  scalapb.gen(grpc = true) -> (Compile / sourceManaged).value / "scalapb",
  scalapb.zio_grpc.ZioCodeGenerator -> (Compile / sourceManaged).value / "scalapb"
)
