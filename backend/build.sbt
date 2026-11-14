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
Compile / mainClass := Some("spaceapps.Main")
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
