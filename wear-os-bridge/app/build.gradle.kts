plugins {
    id("com.android.application")
    id("org.jetbrains.kotlin.android")
}

android {
    namespace = "org.bioorbit.watchbridge"
    compileSdk = 35

    defaultConfig {
        applicationId = "org.bioorbit.watchbridge"
        minSdk = 30
        targetSdk = 35
        versionCode = 1
        versionName = "1.0"
    }
}
