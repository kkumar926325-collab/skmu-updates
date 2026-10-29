package com.skmu.updates

import android.Manifest
import android.app.NotificationManager
import android.app.PendingIntent
import android.content.Context
import android.content.Intent
import android.content.pm.PackageManager
import android.os.Build
import androidx.core.app.NotificationCompat
import androidx.core.app.NotificationManagerCompat
import androidx.core.content.ContextCompat
import androidx.work.Worker
import androidx.work.WorkerParameters
import org.json.JSONObject
import java.net.HttpURLConnection
import java.net.URL

/**
 * Har ~15 minute me server se sabse nayi post ki id puchhta hai.
 * Nayi post mile to notification dikhata hai. (Firebase ki zaroorat nahi.)
 */
class PollWorker(private val ctx: Context, params: WorkerParameters) : Worker(ctx, params) {

    override fun doWork(): Result {
        return try {
            val conn = URL(Config.BASE_URL + "/api/latest").openConnection() as HttpURLConnection
            conn.connectTimeout = 15000
            conn.readTimeout = 15000
            val text = try {
                if (conn.responseCode != 200) return Result.retry()
                conn.inputStream.bufferedReader(Charsets.UTF_8).use { it.readText() }
            } finally {
                conn.disconnect()
            }
            val json = JSONObject(text)
            val id = json.optInt("id", 0)

            val sp = ctx.getSharedPreferences("skmu_prefs", Context.MODE_PRIVATE)
            val last = sp.getInt("last_post_id", -1)

            if (last == -1) {
                // pehli baar: purani posts par notification nahi
                sp.edit().putInt("last_post_id", id).apply()
            } else if (id > last) {
                sp.edit().putInt("last_post_id", id).apply()
                showNotification(json.optString("category"), json.optString("title"))
            } else if (id < last) {
                // post hat gayi thi, counter theek karo
                sp.edit().putInt("last_post_id", id).apply()
            }
            Result.success()
        } catch (e: Exception) {
            Result.retry()
        }
    }

    private fun showNotification(category: String, title: String) {
        if (Build.VERSION.SDK_INT >= 33 &&
            ContextCompat.checkSelfPermission(ctx, Manifest.permission.POST_NOTIFICATIONS)
            != PackageManager.PERMISSION_GRANTED
        ) return

        val open = PendingIntent.getActivity(
            ctx, 0, Intent(ctx, MainActivity::class.java).addFlags(Intent.FLAG_ACTIVITY_SINGLE_TOP),
            PendingIntent.FLAG_UPDATE_CURRENT or PendingIntent.FLAG_IMMUTABLE
        )
        val n = NotificationCompat.Builder(ctx, CHANNEL_ID)
            .setSmallIcon(R.drawable.ic_notify)
            .setContentTitle(if (category.isNotEmpty()) "SKMU • $category" else "SKMU Updates")
            .setContentText(title)
            .setStyle(NotificationCompat.BigTextStyle().bigText(title))
            .setContentIntent(open)
            .setAutoCancel(true)
            .setPriority(NotificationCompat.PRIORITY_DEFAULT)
            .build()
        NotificationManagerCompat.from(ctx).notify(1001, n)
    }

    companion object {
        const val CHANNEL_ID = "skmu_updates"
    }
}
