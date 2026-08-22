using UnityEngine;
using UnityEngine.Networking;
using System;
using System.Collections;

/// <summary>
/// Unity client: calls Web GET /trip, parses current trip origin, destination, and departure time for map simulation.
/// </summary>
public class TripFetcher : MonoBehaviour
{
    [Header("API Config")]
    [Tooltip("Web base URL. Production: https://sunlight-city-blush.vercel.app; Local: http://localhost:8000")]
    [SerializeField] private string baseUrl = "https://sunlight-city-blush.vercel.app";

    [Tooltip("Trip endpoint path. Vercel: /api/trip; local uvicorn: /trip")]
    [SerializeField] private string tripPath = "/api/trip";

    [Tooltip("Required when not logged in; must match anonymous_id used when creating the trip via POST")]
    [SerializeField] private string anonymousId = "";

    [Header("Optional: Bearer token when logged in")]
    [SerializeField] private string bearerToken = "";

    /// <summary>Current trip data (set after a successful fetch).</summary>
    public TripData CurrentTrip { get; private set; }

    /// <summary>Fired when fetch succeeds; argument is the trip (origin, destination, departure).</summary>
    public event Action<TripData> OnTripReceived;

    /// <summary>Fired when fetch fails; argument is the error message.</summary>
    public event Action<string> OnTripFailed;

    /// <summary>
    /// Request latest trip (GET /trip). When logged in pass token; when anonymous, set anonymousId in Inspector or pass here.
    /// </summary>
    public void FetchTrip(string overrideAnonymousId = null)
    {
        StartCoroutine(FetchTripCoroutine(overrideAnonymousId));
    }

    private IEnumerator FetchTripCoroutine(string overrideAnonymousId)
    {
        string path = tripPath.StartsWith("/") ? tripPath : "/" + tripPath;
        string url = baseUrl.TrimEnd('/') + path;
        bool hasAuth = !string.IsNullOrEmpty(bearerToken);
        string anonId = overrideAnonymousId ?? anonymousId;

        if (!hasAuth && string.IsNullOrEmpty(anonId))
        {
            OnTripFailed?.Invoke("Set anonymous_id when not logged in, or provide a Bearer token.");
            yield break;
        }

        if (!hasAuth)
            url += "?anonymous_id=" + UnityWebRequest.EscapeURL(anonId.Trim());

        using (var request = UnityWebRequest.Get(url))
        {
            if (hasAuth)
                request.SetRequestHeader("Authorization", "Bearer " + bearerToken);
            request.SetRequestHeader("Accept", "application/json");

            yield return request.SendWebRequest();

            if (request.result == UnityWebRequest.Result.Success)
            {
                try
                {
                    var trip = JsonUtility.FromJson<TripData>(request.downloadHandler.text);
                    CurrentTrip = trip;
                    OnTripReceived?.Invoke(trip);
                }
                catch (Exception e)
                {
                    OnTripFailed?.Invoke("Failed to parse response: " + e.Message);
                }
            }
            else
            {
                var msg = request.responseCode + " " + request.error;
                if (request.downloadHandler?.text != null)
                    msg += " " + request.downloadHandler.text;
                OnTripFailed?.Invoke(msg);
            }
        }
    }

    // --- DTOs matching FastAPI TripOut (field names must match JSON) ---

    [Serializable]
    public class LatLng
    {
        public float lat;
        public float lng;
    }

    [Serializable]
    public class DepartureTime
    {
        public int hour;   // 0-23
        public int minute; // 0-59
    }

    [Serializable]
    public class TripData
    {
        public int id;
        public string user_email;
        public string anonymous_id;
        public LatLng origin;
        public LatLng destination;
        public DepartureTime departure;
        public string created_at;

        /// <summary>Origin as (lng, lat) for Unity.</summary>
        public Vector2 Origin => origin != null ? new Vector2(origin.lng, origin.lat) : Vector2.zero;

        /// <summary>Destination as (lng, lat) for Unity.</summary>
        public Vector2 Destination => destination != null ? new Vector2(destination.lng, destination.lat) : Vector2.zero;

        /// <summary>Departure time (hour, minute).</summary>
        public (int hour, int minute) Departure => departure != null ? (departure.hour, departure.minute) : (0, 0);
    }
}
