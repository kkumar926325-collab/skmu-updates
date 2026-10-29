package com.skmu.updates

import android.app.Application
import android.app.NotificationChannel
import android.app.NotificationManager
import android.os.Build
import androidx.work.Constraints
import androidx.work.ExistingPeriodicWorkPolicy
import androidx.work.NetworkType
import androidx.work.PeriodicWorkRequestBuilder
import androidx.work.WorkManager
import java.util.concurrent.TimeUnit

class SkmuApp : Application() {
    override fun onCreate() {
        super.onCreate()

        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
            val ch = NotificationChannel(
                PollWorker.CHANNEL_ID,
                "Naye updates",
                NotificationManager.IMPORTANCE_DEFAULT
            )
            ch.description = "Admission, result, form aur notice ke naye updates"
            getSystemService(NotificationManager::class.java).createNotificationChannel(ch)
        }

        val req = PeriodicWorkRequestBuilder<PollWorker>(Config.POLL_MINUTES, TimeUnit.MINUTES)
            .setConstraints(
                Constraints.Builder().setRequiredNetworkType(NetworkType.CONNECTED).build()
            )
            .build()
        WorkManager.getInstance(this)
            .enqueueUniquePeriodicWork("skmu_poll", ExistingPeriodicWorkPolicy.KEEP, req)
    }
}
