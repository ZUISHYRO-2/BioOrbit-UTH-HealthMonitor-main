import org.jetbrains.kotlin.gradle.dsl.JvmTarget

plugins {
    id("com.android.application")
    id("org.jetbrains.kotlin.android")
}

android {
    namespace = "org.bioorbit.mobile"
    compileSdk = 35

    defaultConfig {
        applicationId = "org.bioorbit.mobile"
        minSdk = 26
        targetSdk = 35
        versionCode = 7
        versionName = "1.3.3"
    }

    buildTypes {
        release {
            isMinifyEnabled = false
        }
    }

    compileOptions {
        sourceCompatibility = JavaVersion.VERSION_17
        targetCompatibility = JavaVersion.VERSION_17
    }

    // los modelos del detector de rostro no se deben comprimir
    androidResources {
        noCompress += listOf("bin")
    }
}

kotlin {
    compilerOptions {
        jvmTarget.set(JvmTarget.JVM_17)
    }
}

dependencies {
    // Sirve los archivos de la interfaz como https://appassets.androidplatform.net (necesario para la cámara)
    implementation("androidx.webkit:webkit:1.12.1")
}
