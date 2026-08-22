using UnityEngine;
using System.Collections.Generic;
using System.IO;
using System;
using Stopwatch = System.Diagnostics.Stopwatch;
using Mono.Cecil.Cil;

#if UNITY_EDITOR
using UnityEditor;
#endif

public class RoadGraphExtractor : MonoBehaviour
{
    [Header("Input")]
    public GameObject root;

    [Header("Target Area")]
    public Vector2 graphSize = new Vector2(100f, 100f);
    public Vector2 graphCenterOffset = Vector2.zero;
    public float graphRotationY = 0f;

    [Header("Grid Config")]
    public float cellSize = 0.3f;
    [Range(-1f, 1f)] public float minTriangleUpDot = 0.5f;
    public bool reuseCachedGrid = true;
    public int dilationIterations = 2;
    public bool preprocessOnly = false;
    public bool reuseCachedPreprocess = true;
    public bool useCachedBoundingBox = false;

    [Header("Graph Config")]
    public float mergeRadius = 2.5f;

    private int gridWidth;
    private int gridHeight;

    private bool[,] grid;
    private float[,] distance;
    private bool[,] skeleton;

    private Vector2 origin;
    private Vector3 selectionCenter;
    private Quaternion selectionRotation = Quaternion.identity;
    private Vector2 selectionHalfSize;
    private bool[,] cachedGrid;
    private int cachedGridWidth;
    private int cachedGridHeight;
    private Vector2 cachedOrigin;
    private string cachedGridSignature;
    private bool[,] cachedPreprocessedGrid;
    private float[,] cachedDistance;
    private string cachedPreprocessSignature;

    [Header("Gizmo Display")]
    public bool drawGraphGizmos = true;
    public float vertexGizmoRadius = 0.3f;
    public Color areaGizmoColor = Color.yellow;
    public Color vertexGizmoColor = Color.red;
    public Color edgeGizmoColor = Color.green;

    [SerializeField] private List<Vector3> vertices = new List<Vector3>();
    private HashSet<Edge> edges = new HashSet<Edge>();

    [Serializable]
    struct Edge : IEquatable<Edge>
    {
        public int a, b;
        public Edge(int a, int b) { this.a = a; this.b = b; }

        public bool Equals(Edge other) => a == other.a && b == other.b;
        public override bool Equals(object obj) => obj is Edge other && Equals(other);
        public override int GetHashCode() => HashCode.Combine(a, b);
    }

    void AddUndirectedEdge(ICollection<Edge> target, int a, int b)
    {
        if (a == b) return;
        target.Add(new Edge(a, b));
        target.Add(new Edge(b, a));
    }

    string DirectedEdgeKey(int a, int b)
    {
        return a + "_" + b;
    }

    string UndirectedEdgeKey(int a, int b)
    {
        return a < b ? a + "_" + b : b + "_" + a;
    }

    void AddUndirectedEdgeKeys(HashSet<string> target, int a, int b)
    {
        if (a == b) return;
        target.Add(DirectedEdgeKey(a, b));
        target.Add(DirectedEdgeKey(b, a));
    }

    HashSet<Edge> NormalizeUndirectedEdges(IEnumerable<Edge> source)
    {
        HashSet<string> seen = new HashSet<string>();
        HashSet<Edge> normalized = new HashSet<Edge>();

        foreach (var e in source)
        {
            if (e.a == e.b) continue;
            int a = e.a < e.b ? e.a : e.b;
            int b = e.a < e.b ? e.b : e.a;
            string key = UndirectedEdgeKey(a, b);
            if (!seen.Add(key)) continue;
            normalized.Add(new Edge(a, b));
            normalized.Add(new Edge(b, a));
        }

        return normalized;
    }

    bool HasUndirectedEdge(int a, int b)
    {
        return edges.Contains(new Edge(a, b)) || edges.Contains(new Edge(b, a));
    }

    Dictionary<Vector2Int, List<int>> BuildSpatialHash(float queryRadius)
    {
        float hashCellSize = Mathf.Max(queryRadius, 0.001f);
        Dictionary<Vector2Int, List<int>> spatial = new Dictionary<Vector2Int, List<int>>();

        for (int i = 0; i < vertices.Count; i++)
        {
            Vector2Int cell = new Vector2Int(
                Mathf.FloorToInt(vertices[i].x / hashCellSize),
                Mathf.FloorToInt(vertices[i].z / hashCellSize));

            if (!spatial.TryGetValue(cell, out List<int> bucket))
            {
                bucket = new List<int>();
                spatial[cell] = bucket;
            }

            bucket.Add(i);
        }

        return spatial;
    }

    IEnumerable<int> QuerySpatialHash(Dictionary<Vector2Int, List<int>> spatial, Vector3 point, float queryRadius)
    {
        float hashCellSize = Mathf.Max(queryRadius, 0.001f);
        Vector2Int centerCell = new Vector2Int(
            Mathf.FloorToInt(point.x / hashCellSize),
            Mathf.FloorToInt(point.z / hashCellSize));

        for (int dx = -1; dx <= 1; dx++)
        {
            for (int dz = -1; dz <= 1; dz++)
            {
                Vector2Int cell = new Vector2Int(centerCell.x + dx, centerCell.y + dz);
                if (!spatial.TryGetValue(cell, out List<int> bucket)) continue;
                foreach (int i in bucket)
                    yield return i;
            }
        }
    }

    [ContextMenu("Generate Graph + Export JSON")]
    public void Generate()
    {
        if (root == null)
        {
            return;
        }

        Stopwatch totalWatch = Stopwatch.StartNew();
        const int totalStages = 27;
        int currentStage = 0;
        UpdateStageProgress("Starting", currentStage, totalStages);

        try
        {
            if (!EnsurePreprocessedData())
                return;

            if (preprocessOnly)
            {
                totalWatch.Stop();
                return;
            }

            UpdateStageProgress("RemoveShortEdges", ++currentStage, totalStages);
            RunStep("RemoveShortEdges", () => RemoveShortEdges());
            UpdateStageProgress("DeduplicateEdges", ++currentStage, totalStages);
            RunStep("DeduplicateEdges", DeduplicateEdges);
            UpdateStageProgress("RemoveCycles(3)", ++currentStage, totalStages);
            RunStep("RemoveCycles(3)", () => RemoveCycles(3));
            UpdateStageProgress("Connect", ++currentStage, totalStages);
            RunStep("Connect", () => Connect());
            UpdateStageProgress("RemoveCycles(8)", ++currentStage, totalStages);
            RunStep("RemoveCycles(8)", () => RemoveCycles(8));
            UpdateStageProgress("RemoveFloatingNodes", ++currentStage, totalStages);
            RunStep("RemoveFloatingNodes", RemoveFloatingNodes);
            UpdateStageProgress("DeleteOverlapEdges", ++currentStage, totalStages);
            RunStep("DeleteOverlapEdges", () => DeleteOverlapEdges(7.5f));
            UpdateStageProgress("RemoveStraightVertices", ++currentStage, totalStages);
            RunStep("RemoveStraightVertices", () => RemoveStraightVertices(165f, float.MaxValue));
            UpdateStageProgress("SpecialProcess", ++currentStage, totalStages);
            RunStep("SpecialProcess", () => SpecialProcess(20f));
            UpdateStageProgress("Connect", ++currentStage, totalStages);
            RunStep("Connect", () => Connect(true, 50f, 15f));
            UpdateStageProgress("Connect", ++currentStage, totalStages);
            RunStep("Connect", () => Connect(true, 40f, 30f, true));
            UpdateStageProgress("RemoveStraightVertices", ++currentStage, totalStages);
            RunStep("RemoveStraightVertices", () => RemoveStraightVertices(150f, float.MaxValue));
            UpdateStageProgress("FinalCluster", ++currentStage, totalStages);
            RunStep("FinalCluster", () => FinalCluster(15f, true));
            UpdateStageProgress("FinalCluster", ++currentStage, totalStages);
            RunStep("FinalCluster", () => FinalCluster(10f));
            UpdateStageProgress("FinalCluster", ++currentStage, totalStages);
            RunStep("FinalCluster", () => FinalCluster(30f));
            UpdateStageProgress("RemoveCycles(3)", ++currentStage, totalStages);
            RunStep("RemoveCycles(3)", () => RemoveCycles(3));
            UpdateStageProgress("DeleteOverlapEdges", ++currentStage, totalStages);
            RunStep("DeleteOverlapEdges", () => DeleteOverlapEdges(7.5f));
            UpdateStageProgress("RemoveStraightVertices", ++currentStage, totalStages);
            RunStep("RemoveStraightVertices", () => RemoveStraightVertices(150f, float.MaxValue));
            UpdateStageProgress("FinalCluster", ++currentStage, totalStages);
            RunStep("FinalCluster", () => FinalCluster(10f));
            UpdateStageProgress("FinalCluster", ++currentStage, totalStages);
            RunStep("FinalCluster", () => FinalCluster(30f, true));
            UpdateStageProgress("ConnectDegreeThreeVertices", ++currentStage, totalStages);
            RunStep("ConnectDegreeThreeVertices", () => ConnectDegreeThreeVertices(40f, 45f));
            UpdateStageProgress("RemoveCycles(3)", ++currentStage, totalStages);
            RunStep("RemoveCycles(3)", () => RemoveCycles(3));
            UpdateStageProgress("RemoveStraightVertices", ++currentStage, totalStages);
            RunStep("RemoveStraightVertices", () => RemoveStraightVertices(150f, float.MaxValue));
            UpdateStageProgress("FinalCluster", ++currentStage, totalStages);
            RunStep("FinalCluster", () => FinalCluster(20f, true));
            UpdateStageProgress("DeleteOverlapEdges", ++currentStage, totalStages);
            RunStep("DeleteOverlapEdges", () => DeleteOverlapEdges(15f));
            UpdateStageProgress("RemoveEndpoints", ++currentStage, totalStages);
            RunStep("RemoveEndpoints", () => RemoveEndpoints());
            UpdateStageProgress("ExportJson", ++currentStage, totalStages);
            RunStep("ExportJson", ExportJson);
            totalWatch.Stop();
            UpdateStageProgress("Done", totalStages, totalStages);
        }
        finally
        {
            ClearEditorProgress();
        }
    }

    bool RunStep(string name, Func<bool> step)
    {
        Stopwatch watch = Stopwatch.StartNew();
        bool ok = step();
        watch.Stop();
        return ok;
    }

    void RunStep(string name, Action step)
    {
        Stopwatch watch = Stopwatch.StartNew();
        step();
        watch.Stop();
    }

    string FormatElapsed(TimeSpan elapsed)
    {
        return $"{elapsed.TotalMilliseconds:F2} ms";
    }

    bool EnsurePreprocessedData()
    {
        if (useCachedBoundingBox)
            TryApplyCachedBoundingBox();

        if (!TryGetGraphBounds(out Bounds graphBounds))
        {
            return false;
        }

        float minX = graphBounds.min.x;
        float maxX = graphBounds.max.x;
        float minZ = graphBounds.min.z;
        float maxZ = graphBounds.max.z;

        origin = new Vector2(minX, minZ);
        gridWidth = Mathf.CeilToInt((maxX - minX) / cellSize);
        gridHeight = Mathf.CeilToInt((maxZ - minZ) / cellSize);

        if (TryLoadPreprocessCache(minX, maxX, minZ, maxZ))
            return true;

        string preprocessSignature = ComputePreprocessSignature(minX, maxX, minZ, maxZ);
        if (reuseCachedPreprocess &&
            cachedPreprocessedGrid != null &&
            cachedDistance != null &&
            cachedPreprocessSignature == preprocessSignature)
        {
            grid = (bool[,])cachedPreprocessedGrid.Clone();
            distance = (float[,])cachedDistance.Clone();
            UpdateEditorProgress("RoadGraphExtractor", "Reusing cached preprocess data", 0.25f);
            return true;
        }

        if (!RunStep("BuildGrid", BuildGrid))
            return false;
        RunStep("DilateGrid", () => DilateGrid(dilationIterations));
        RunStep("ComputeDistanceTransform", ComputeDistanceTransform);
        RunStep("ExtractRidgeSkeleton", ExtractRidgeSkeleton);
        vertices.Clear();
        edges.Clear();
        RunStep("ExtractGraph", ExtractGraph);
        RunStep("ClusterNodes", ClusterNodes);
        CachePreprocessedData(preprocessSignature);
        SavePreprocessCache(minX, maxX, minZ, maxZ);
        return true;
    }

    void UpdateStageProgress(string stageName, int currentStage, int totalStages)
    {
        float progress = totalStages <= 0 ? 0f : currentStage / (float)totalStages;
        UpdateEditorProgress("RoadGraphExtractor", stageName, progress);
    }

    string ComputePreprocessSignature(float minX, float maxX, float minZ, float maxZ)
    {
        return string.Join("|",
            ComputeGridSignature(minX, maxX, minZ, maxZ),
            dilationIterations);
    }

    // ================= GRID =================
    bool BuildGrid()
    {
        if (!TryGetGraphBounds(out Bounds graphBounds))
        {
            return false;
        }

        float minX = graphBounds.min.x;
        float maxX = graphBounds.max.x;
        float minZ = graphBounds.min.z;
        float maxZ = graphBounds.max.z;

        origin = new Vector2(minX, minZ);
        gridWidth = Mathf.CeilToInt((maxX - minX) / cellSize);
        gridHeight = Mathf.CeilToInt((maxZ - minZ) / cellSize);

        string gridSignature = ComputeGridSignature(minX, maxX, minZ, maxZ);
        if (reuseCachedGrid &&
            cachedGrid != null &&
            cachedGridSignature == gridSignature &&
            cachedGridWidth == gridWidth &&
            cachedGridHeight == gridHeight &&
            cachedOrigin == origin)
        {
            grid = (bool[,])cachedGrid.Clone();
            return true;
        }
        
        // Safety cap to avoid memory issues (e.g., 25M cells)
        // if (gridWidth * gridHeight > 25000000) 
        // {
        //     Debug.LogError("Grid too large! Increase cell size or decrease padding. Total cells attempted: " + (gridWidth * gridHeight));
        //     return false;
        // }

        grid = new bool[gridWidth, gridHeight];

        // Only process meshes that could be in our bounding box
        Bounds bbox = new Bounds(
            new Vector3((minX + maxX) * 0.5f, 0, (minZ + maxZ) * 0.5f),
            new Vector3(maxX - minX, 1000f, maxZ - minZ)
        );

        MeshFilter[] meshFilters = root.GetComponentsInChildren<MeshFilter>();
        int totalTriangleCount = 0;
        foreach (var mf in meshFilters)
        {
            var renderer = mf.GetComponent<MeshRenderer>();
            if (renderer != null && !bbox.Intersects(renderer.bounds)) continue;

            var mesh = mf.sharedMesh;
            if (mesh == null || !mesh.isReadable) continue;
            totalTriangleCount += mesh.triangles.Length / 3;
        }

        int processedTriangles = 0;
        int triangleProgressStep = Mathf.Max(1, totalTriangleCount / 100);

        foreach (var mf in meshFilters)
        {
            var renderer = mf.GetComponent<MeshRenderer>();
            if (renderer != null && !bbox.Intersects(renderer.bounds)) continue;

            var mesh = mf.sharedMesh;
            if (mesh == null || !mesh.isReadable) continue;

            var verts = mesh.vertices;
            var tris = mesh.triangles;
            Matrix4x4 localToWorld = mf.transform.localToWorldMatrix;
            Vector3[] worldVerts = new Vector3[verts.Length];

            for (int i = 0; i < verts.Length; i++)
                worldVerts[i] = localToWorld.MultiplyPoint3x4(verts[i]);

            for (int i = 0; i < tris.Length; i += 3)
            {
                Vector3 v0 = worldVerts[tris[i]];
                Vector3 v1 = worldVerts[tris[i + 1]];
                Vector3 v2 = worldVerts[tris[i + 2]];

                if (!ShouldRasterizeTriangle(v0, v1, v2, minX, maxX, minZ, maxZ))
                {
                    processedTriangles++;
                    if (processedTriangles % triangleProgressStep == 0 || processedTriangles == totalTriangleCount)
                        LogProgressBar("BuildGrid", processedTriangles, totalTriangleCount);
                    continue;
                }

                RasterizeTriangle(v0, v1, v2);
                processedTriangles++;
                if (processedTriangles % triangleProgressStep == 0 || processedTriangles == totalTriangleCount)
                    LogProgressBar("BuildGrid", processedTriangles, totalTriangleCount);
            }
        }

        LogProgressBar("BuildGrid", totalTriangleCount, totalTriangleCount);

        CacheGrid(gridSignature);
        return true;
    }

    string ComputeGridSignature(float minX, float maxX, float minZ, float maxZ)
    {
        return string.Join("|",
            root != null ? root.GetInstanceID() : 0,
            graphSize.x, graphSize.y,
            cellSize, minTriangleUpDot,
            minX, maxX, minZ, maxZ);
    }

    void CacheGrid(string gridSignature)
    {
        cachedGrid = (bool[,])grid.Clone();
        cachedGridWidth = gridWidth;
        cachedGridHeight = gridHeight;
        cachedOrigin = origin;
        cachedGridSignature = gridSignature;
    }

    void CachePreprocessedData(string preprocessSignature)
    {
        cachedPreprocessedGrid = (bool[,])grid.Clone();
        cachedDistance = (float[,])distance.Clone();
        cachedPreprocessSignature = preprocessSignature;
    }

    string GetPreprocessCachePath()
    {
        return Path.Combine(Directory.GetCurrentDirectory(), "road_graph_preprocess_cache.bin");
    }

    bool TryApplyCachedBoundingBox()
    {
        if (root == null) return false;

        string path = GetPreprocessCachePath();
        if (!File.Exists(path)) return false;
        if (!TryGetRootBounds(out Bounds rootBounds)) return false;

        try
        {
            using (BinaryReader br = new BinaryReader(File.OpenRead(path)))
            {
                if (br.ReadString() != "RGP1") return false;

                float fileMinX = br.ReadSingle();
                float fileMaxX = br.ReadSingle();
                float fileMinZ = br.ReadSingle();
                float fileMaxZ = br.ReadSingle();

                Vector3 cachedCenter = new Vector3((fileMinX + fileMaxX) * 0.5f, 0f, (fileMinZ + fileMaxZ) * 0.5f);
                Vector3 rootCenter = rootBounds.center;

                graphSize = new Vector2(fileMaxX - fileMinX, fileMaxZ - fileMinZ);
                graphCenterOffset = new Vector2(cachedCenter.x - rootCenter.x, cachedCenter.z - rootCenter.z);
                graphRotationY = 0f;
                return true;
            }
        }
        catch
        {
            return false;
        }
    }

    bool TryLoadPreprocessCache(float minX, float maxX, float minZ, float maxZ)
    {
        if (!reuseCachedPreprocess) return false;

        string path = GetPreprocessCachePath();
        if (!File.Exists(path)) return false;

        try
        {
            using (BinaryReader br = new BinaryReader(File.OpenRead(path)))
            {
                if (br.ReadString() != "RGP1") return false;

                float fileMinX = br.ReadSingle();
                float fileMaxX = br.ReadSingle();
                float fileMinZ = br.ReadSingle();
                float fileMaxZ = br.ReadSingle();
                float fileCellSize = br.ReadSingle();
                float fileMinTriangleUpDot = br.ReadSingle();
                int fileDilationIterations = br.ReadInt32();
                int fileGridWidth = br.ReadInt32();
                int fileGridHeight = br.ReadInt32();
                float fileOriginX = br.ReadSingle();
                float fileOriginY = br.ReadSingle();

                if (!Mathf.Approximately(fileMinX, minX) ||
                    !Mathf.Approximately(fileMaxX, maxX) ||
                    !Mathf.Approximately(fileMinZ, minZ) ||
                    !Mathf.Approximately(fileMaxZ, maxZ) ||
                    !Mathf.Approximately(fileCellSize, cellSize) ||
                    !Mathf.Approximately(fileMinTriangleUpDot, minTriangleUpDot) ||
                    fileDilationIterations != dilationIterations ||
                    fileGridWidth != gridWidth ||
                    fileGridHeight != gridHeight ||
                    !Mathf.Approximately(fileOriginX, origin.x) ||
                    !Mathf.Approximately(fileOriginY, origin.y))
                    return false;

                bool[,] loadedGrid = new bool[gridWidth, gridHeight];
                float[,] loadedDistance = new float[gridWidth, gridHeight];

                for (int y = 0; y < gridHeight; y++)
                    for (int x = 0; x < gridWidth; x++)
                        loadedGrid[x, y] = br.ReadBoolean();

                for (int y = 0; y < gridHeight; y++)
                    for (int x = 0; x < gridWidth; x++)
                        loadedDistance[x, y] = br.ReadSingle();

                int vertexCount = br.ReadInt32();
                List<Vector3> loadedVertices = new List<Vector3>(vertexCount);
                for (int i = 0; i < vertexCount; i++)
                    loadedVertices.Add(new Vector3(br.ReadSingle(), br.ReadSingle(), br.ReadSingle()));

                int edgeCount = br.ReadInt32();
                HashSet<Edge> loadedEdges = new HashSet<Edge>();
                for (int i = 0; i < edgeCount; i++)
                {
                    loadedEdges.Add(new Edge(br.ReadInt32(), br.ReadInt32()));
                }

                grid = loadedGrid;
                distance = loadedDistance;
                vertices = loadedVertices;
                edges = NormalizeUndirectedEdges(loadedEdges);

                string preprocessSignature = ComputePreprocessSignature(minX, maxX, minZ, maxZ);
                CacheGrid(ComputeGridSignature(minX, maxX, minZ, maxZ));
                CachePreprocessedData(preprocessSignature);
                return true;
            }
        }
        catch
        {
            return false;
        }
    }

    void SavePreprocessCache(float minX, float maxX, float minZ, float maxZ)
    {
        if (grid == null || distance == null || vertices == null || edges == null) return;

        string path = GetPreprocessCachePath();
        try
        {
            string folder = Path.GetDirectoryName(path);
            if (!string.IsNullOrEmpty(folder) && !Directory.Exists(folder))
                Directory.CreateDirectory(folder);

            using (BinaryWriter bw = new BinaryWriter(File.Open(path, FileMode.Create, FileAccess.Write)))
            {
                bw.Write("RGP1");
                bw.Write(minX);
                bw.Write(maxX);
                bw.Write(minZ);
                bw.Write(maxZ);
                bw.Write(cellSize);
                bw.Write(minTriangleUpDot);
                bw.Write(dilationIterations);
                bw.Write(gridWidth);
                bw.Write(gridHeight);
                bw.Write(origin.x);
                bw.Write(origin.y);

                for (int y = 0; y < gridHeight; y++)
                    for (int x = 0; x < gridWidth; x++)
                        bw.Write(grid[x, y]);

                for (int y = 0; y < gridHeight; y++)
                    for (int x = 0; x < gridWidth; x++)
                        bw.Write(distance[x, y]);

                bw.Write(vertices.Count);
                foreach (var v in vertices)
                {
                    bw.Write(v.x);
                    bw.Write(v.y);
                    bw.Write(v.z);
                }

                bw.Write(edges.Count);
                foreach (var e in edges)
                {
                    bw.Write(e.a);
                    bw.Write(e.b);
                }
            }
        }
        catch
        {
        }
    }

    bool ShouldRasterizeTriangle(Vector3 v0, Vector3 v1, Vector3 v2,
                                 float minX, float maxX, float minZ, float maxZ)
    {
        Vector3 lv0 = ToSelectionLocal(v0);
        Vector3 lv1 = ToSelectionLocal(v1);
        Vector3 lv2 = ToSelectionLocal(v2);

        float triMinX = Mathf.Min(lv0.x, Mathf.Min(lv1.x, lv2.x));
        float triMaxX = Mathf.Max(lv0.x, Mathf.Max(lv1.x, lv2.x));
        float triMinZ = Mathf.Min(lv0.z, Mathf.Min(lv1.z, lv2.z));
        float triMaxZ = Mathf.Max(lv0.z, Mathf.Max(lv1.z, lv2.z));

        if (triMaxX < -selectionHalfSize.x || triMinX > selectionHalfSize.x ||
            triMaxZ < -selectionHalfSize.y || triMinZ > selectionHalfSize.y)
            return false;

        Vector3 normal = Vector3.Cross(v1 - v0, v2 - v0);
        float normalMagnitudeSq = normal.sqrMagnitude;
        if (normalMagnitudeSq < 1e-8f)
            return false;

        float upDot = normal.y / Mathf.Sqrt(normalMagnitudeSq);
        return upDot >= minTriangleUpDot;
    }

    bool TryGetGraphBounds(out Bounds graphBounds)
    {
        graphBounds = default;

        if (!TryGetRootBounds(out Bounds rootBounds))
            return false;

        graphBounds = rootBounds;
        Vector3 rootCenter = graphBounds.center;
        selectionCenter = rootCenter + new Vector3(graphCenterOffset.x, 0f, graphCenterOffset.y);
        selectionRotation = Quaternion.Euler(0f, graphRotationY, 0f);
        selectionHalfSize = new Vector2(
            Mathf.Max(graphSize.x, cellSize) * 0.5f,
            Mathf.Max(graphSize.y, cellSize) * 0.5f
        );

        Vector3[] corners = GetSelectionCorners();
        Vector3 min = corners[0];
        Vector3 max = corners[0];
        for (int i = 1; i < corners.Length; i++)
        {
            min = Vector3.Min(min, corners[i]);
            max = Vector3.Max(max, corners[i]);
        }

        float height = Mathf.Max(graphBounds.size.y, 1f);
        graphBounds = new Bounds(
            new Vector3((min.x + max.x) * 0.5f, rootCenter.y, (min.z + max.z) * 0.5f),
            new Vector3(max.x - min.x, height, max.z - min.z)
        );
        return true;
    }

    bool TryGetRootBounds(out Bounds graphBounds)
    {
        graphBounds = default;

        if (root == null) return false;

        bool hasBounds = false;

        foreach (var renderer in root.GetComponentsInChildren<Renderer>())
        {
            if (!hasBounds)
            {
                graphBounds = renderer.bounds;
                hasBounds = true;
            }
            else
            {
                graphBounds.Encapsulate(renderer.bounds);
            }
        }

        if (!hasBounds)
        {
            foreach (var mf in root.GetComponentsInChildren<MeshFilter>())
            {
                var mesh = mf.sharedMesh;
                if (mesh == null) continue;

                Bounds meshBounds = TransformBounds(mf.transform.localToWorldMatrix, mesh.bounds);
                if (!hasBounds)
                {
                    graphBounds = meshBounds;
                    hasBounds = true;
                }
                else
                {
                    graphBounds.Encapsulate(meshBounds);
                }
            }
        }

        return hasBounds;
    }

    Vector3[] GetSelectionCorners()
    {
        Vector3[] corners = new Vector3[4];
        Vector3[] localCorners =
        {
            new Vector3(-selectionHalfSize.x, 0f, -selectionHalfSize.y),
            new Vector3(-selectionHalfSize.x, 0f,  selectionHalfSize.y),
            new Vector3( selectionHalfSize.x, 0f,  selectionHalfSize.y),
            new Vector3( selectionHalfSize.x, 0f, -selectionHalfSize.y)
        };

        for (int i = 0; i < 4; i++)
            corners[i] = selectionCenter + selectionRotation * localCorners[i];

        return corners;
    }

    Vector3 ToSelectionLocal(Vector3 worldPoint)
    {
        return Quaternion.Inverse(selectionRotation) * (worldPoint - selectionCenter);
    }

    bool IsInsideSelectionArea(Vector3 worldPoint)
    {
        Vector3 local = ToSelectionLocal(worldPoint);
        return Mathf.Abs(local.x) <= selectionHalfSize.x &&
               Mathf.Abs(local.z) <= selectionHalfSize.y;
    }

    Bounds TransformBounds(Matrix4x4 matrix, Bounds localBounds)
    {
        Vector3 center = matrix.MultiplyPoint3x4(localBounds.center);
        Vector3 extents = localBounds.extents;

        Vector3 axisX = matrix.MultiplyVector(new Vector3(extents.x, 0f, 0f));
        Vector3 axisY = matrix.MultiplyVector(new Vector3(0f, extents.y, 0f));
        Vector3 axisZ = matrix.MultiplyVector(new Vector3(0f, 0f, extents.z));

        Vector3 worldExtents = new Vector3(
            Mathf.Abs(axisX.x) + Mathf.Abs(axisY.x) + Mathf.Abs(axisZ.x),
            Mathf.Abs(axisX.y) + Mathf.Abs(axisY.y) + Mathf.Abs(axisZ.y),
            Mathf.Abs(axisX.z) + Mathf.Abs(axisY.z) + Mathf.Abs(axisZ.z)
        );

        return new Bounds(center, worldExtents * 2f);
    }

    void RasterizeTriangle(Vector3 v0, Vector3 v1, Vector3 v2)
    {
        Vector2 p0 = ToGrid(v0);
        Vector2 p1 = ToGrid(v1);
        Vector2 p2 = ToGrid(v2);

        int minY = Mathf.Clamp(Mathf.FloorToInt(Mathf.Min(p0.y, Mathf.Min(p1.y, p2.y))), 0, gridHeight - 1);
        int maxY = Mathf.Clamp(Mathf.CeilToInt(Mathf.Max(p0.y, Mathf.Max(p1.y, p2.y))), 0, gridHeight - 1);

        for (int y = minY; y <= maxY; y++)
        {
            float sampleY = y + 0.5f;
            int intersectionCount = 0;
            float x0 = 0f;
            float x1 = 0f;

            AddScanlineIntersection(p0, p1, sampleY, ref intersectionCount, ref x0, ref x1);
            AddScanlineIntersection(p1, p2, sampleY, ref intersectionCount, ref x0, ref x1);
            AddScanlineIntersection(p2, p0, sampleY, ref intersectionCount, ref x0, ref x1);

            if (intersectionCount < 2) continue;

            if (x0 > x1)
            {
                float temp = x0;
                x0 = x1;
                x1 = temp;
            }

            int minX = Mathf.Clamp(Mathf.CeilToInt(x0 - 0.5f), 0, gridWidth - 1);
            int maxX = Mathf.Clamp(Mathf.FloorToInt(x1 - 0.5f), 0, gridWidth - 1);

            for (int x = minX; x <= maxX; x++)
            {
                Vector3 worldPos = ToWorld(x, y);
                if (IsInsideSelectionArea(worldPos))
                    grid[x, y] = true;
            }
        }
    }

    void AddScanlineIntersection(Vector2 a, Vector2 b, float sampleY,
                                 ref int intersectionCount, ref float x0, ref float x1)
    {
        if (Mathf.Abs(a.y - b.y) < 1e-5f) return;

        float minY = Mathf.Min(a.y, b.y);
        float maxY = Mathf.Max(a.y, b.y);

        if (sampleY < minY || sampleY >= maxY) return;

        float t = (sampleY - a.y) / (b.y - a.y);
        float x = Mathf.Lerp(a.x, b.x, t);

        if (intersectionCount == 0) x0 = x;
        else if (intersectionCount == 1) x1 = x;

        intersectionCount++;
    }

    Vector2 ToGrid(Vector3 w)
    {
        return new Vector2(
            (w.x - origin.x) / cellSize,
            (w.z - origin.y) / cellSize
        );
    }

    bool PointInTriangle(Vector2 p, Vector2 a, Vector2 b, Vector2 c)
    {
        float area = Cross(b-a,c-a);
        if (Mathf.Abs(area) < 1e-5f) return false;

        float s = Cross(p-a,c-a)/area;
        float t = Cross(b-a,p-a)/area;

        return s>=0 && t>=0 && s+t<=1;
    }

    float Cross(Vector2 a, Vector2 b)
    {
        return a.x*b.y - a.y*b.x;
    }

    // ================= 🔥 DILATION =================
    void DilateGrid(int iter)
    {
        int totalRows = Mathf.Max(1, iter * Mathf.Max(0, gridWidth - 2));
        int processedRows = 0;
        int rowProgressStep = Mathf.Max(1, totalRows / 100);

        for (int k = 0; k < iter; k++)
        {
            bool[,] temp = (bool[,])grid.Clone();

            for (int x=1;x<gridWidth-1;x++)
            {
            for (int y=1;y<gridHeight-1;y++)
            {
                if (!grid[x,y])
                {
                    foreach (var d in Directions8())
                    {
                        if (grid[x+d.x,y+d.y])
                        {
                            temp[x,y]=true;
                            break;
                        }
                    }
                }
            }
                processedRows++;
                if (processedRows % rowProgressStep == 0 || processedRows == totalRows)
                    LogProgressBar("DilateGrid", processedRows, totalRows);
            }

            grid = temp;
        }
    }

    // ================= DISTANCE =================
    void ComputeDistanceTransform()
    {
        distance = new float[gridWidth,gridHeight];
        int totalCells = gridWidth * gridHeight;
        int initProcessed = 0;
        int initProgressStep = Mathf.Max(1, totalCells / 10);

        for(int x=0;x<gridWidth;x++)
        for(int y=0;y<gridHeight;y++)
        {
            if(!grid[x,y])
            {
                distance[x,y]=0;
            }
            else distance[x,y]=float.MaxValue;

            initProcessed++;
            if (initProcessed % initProgressStep == 0 || initProcessed == totalCells)
                LogProgressBar("ComputeDistanceTransform Init", initProcessed, totalCells);
        }

        int totalPasses = Mathf.Max(1, totalCells * 2);
        int relaxProcessed = 0;
        int relaxProgressStep = Mathf.Max(1, totalPasses / 100);

        // Forward pass
        for (int x = 0; x < gridWidth; x++)
        {
            for (int y = 0; y < gridHeight; y++)
            {
                if (distance[x, y] > 0f)
                {
                    RelaxDistance(x, y, x - 1, y, 1f);
                    RelaxDistance(x, y, x, y - 1, 1f);
                    RelaxDistance(x, y, x - 1, y - 1, 1.41421356f);
                    RelaxDistance(x, y, x - 1, y + 1, 1.41421356f);
                }

                relaxProcessed++;
                if (relaxProcessed % relaxProgressStep == 0 || relaxProcessed == totalPasses)
                    LogProgressBar("ComputeDistanceTransform", relaxProcessed, totalPasses);
            }
        }

        // Backward pass
        for (int x = gridWidth - 1; x >= 0; x--)
        {
            for (int y = gridHeight - 1; y >= 0; y--)
            {
                if (distance[x, y] > 0f)
                {
                    RelaxDistance(x, y, x + 1, y, 1f);
                    RelaxDistance(x, y, x, y + 1, 1f);
                    RelaxDistance(x, y, x + 1, y + 1, 1.41421356f);
                    RelaxDistance(x, y, x + 1, y - 1, 1.41421356f);
                }

                relaxProcessed++;
                if (relaxProcessed % relaxProgressStep == 0 || relaxProcessed == totalPasses)
                    LogProgressBar("ComputeDistanceTransform", relaxProcessed, totalPasses);
            }
        }
    }

    void RelaxDistance(int x, int y, int nx, int ny, float cost)
    {
        if (!InBounds(nx, ny)) return;
        float nd = distance[nx, ny] + cost;
        if (nd < distance[x, y])
            distance[x, y] = nd;
    }

    void LogProgressBar(string label, int current, int total)
    {
        total = Mathf.Max(total, 1);
        current = Mathf.Clamp(current, 0, total);
        UpdateEditorProgress("RoadGraphExtractor", label, current / (float)total);
    }

    void UpdateEditorProgress(string title, string info, float progress)
    {
#if UNITY_EDITOR
        EditorUtility.DisplayProgressBar(title, info, Mathf.Clamp01(progress));
#endif
    }

    void ClearEditorProgress()
    {
#if UNITY_EDITOR
        EditorUtility.ClearProgressBar();
#endif
    }

    void ExtractRidgeSkeleton()
    {
        skeleton = new bool[gridWidth,gridHeight];
        int totalRows = Mathf.Max(1, gridWidth - 2);
        int rowStep = Mathf.Max(1, totalRows / 100);

        for(int x=1;x<gridWidth-1;x++)
        {
        for(int y=1;y<gridHeight-1;y++)
        {
            if(!grid[x,y]) continue;

            float d=distance[x,y];
            bool max=true;

            foreach(var dir in Directions8())
                if(distance[x+dir.x,y+dir.y]>d) max=false;

            if(max) skeleton[x,y]=true;
        }
            int processed = x;
            if (processed % rowStep == 0 || processed == gridWidth - 2)
                LogProgressBar("ExtractRidgeSkeleton", processed, totalRows);
        }
    }

    // ================= 🔥 GRAPH =================
    void ExtractGraph()
    {
        vertices.Clear();
        edges.Clear();

        int[,] nodeIds = new int[gridWidth, gridHeight];
        int totalRows = Mathf.Max(1, gridWidth * 2);
        int progressStep = Mathf.Max(1, totalRows / 100);
        int processedRows = 0;
        for (int x = 0; x < gridWidth; x++)
        for (int y = 0; y < gridHeight; y++)
            nodeIds[x, y] = -1;

        // Step 1: create a vertex for EVERY skeleton pixel
        for(int x=0;x<gridWidth;x++)
        {
        for(int y=0;y<gridHeight;y++)
        {
            if(!skeleton[x,y]) continue;

            int id = vertices.Count;
            nodeIds[x, y] = id;
            vertices.Add(ToWorld(x,y));
        }
            processedRows++;
            if (processedRows % progressStep == 0 || processedRows == totalRows)
                LogProgressBar("ExtractGraph", processedRows, totalRows);
        }

        // Step 2: connect neighbors
        for (int x = 0; x < gridWidth; x++)
        {
        for (int y = 0; y < gridHeight; y++)
        {
            int a = nodeIds[x, y];
            if (a == -1) continue;

            AddEdgeIfValid(nodeIds, a, x + 1, y);
            AddEdgeIfValid(nodeIds, a, x, y + 1);
            AddEdgeIfValid(nodeIds, a, x + 1, y + 1);
            AddEdgeIfValid(nodeIds, a, x + 1, y - 1);
        }
            processedRows++;
            if (processedRows % progressStep == 0 || processedRows == totalRows)
                LogProgressBar("ExtractGraph", processedRows, totalRows);
        }
    }

    void AddEdgeIfValid(int[,] nodeIds, int a, int x, int y)
    {
        if (!InBounds(x, y)) return;

        int b = nodeIds[x, y];
        if (b == -1 || a == b) return;

        AddUndirectedEdge(edges, a, b);
    }

    Vector3 ToWorld(int x,int y)
    {
        return new Vector3(x*cellSize+origin.x,0,y*cellSize+origin.y);
    }

    bool InBounds(int x,int y)
    {
        return x>=0&&y>=0&&x<gridWidth&&y<gridHeight;
    }

    Vector2Int[] Directions8()
    {
        return new Vector2Int[]{
            new Vector2Int(1,0),new Vector2Int(-1,0),
            new Vector2Int(0,1),new Vector2Int(0,-1),
            new Vector2Int(1,1),new Vector2Int(1,-1),
            new Vector2Int(-1,1),new Vector2Int(-1,-1)};
    }

    // ================= CLEAN =================
    void ClusterNodes()
    {
        List<Vector3> newV=new List<Vector3>();
        int[] map=new int[vertices.Count];
        bool[] used=new bool[vertices.Count];
        int total = Mathf.Max(1, vertices.Count);
        int step = Mathf.Max(1, total / 100);

        for(int i=0;i<vertices.Count;i++)
        {
            if(used[i]) continue;

            Vector3 sum=vertices[i];
            int count=1;
            used[i]=true;

            for(int j=i+1;j<vertices.Count;j++)
            {
                if(used[j]) continue;
                if(Vector3.Distance(vertices[i],vertices[j])<mergeRadius)
                {
                    sum+=vertices[j];
                    count++;
                    used[j]=true;
                    map[j]=newV.Count;
                }
            }

            map[i]=newV.Count;
            newV.Add(sum/count);

            int processed = i + 1;
            if (processed % step == 0 || processed == total)
                LogProgressBar("ClusterNodes", processed, total);
        }

        HashSet<Edge> newE=new HashSet<Edge>();
        foreach(var e in edges)
        {
            int a=map[e.a], b=map[e.b];
            if(a!=b)
                AddUndirectedEdge(newE, a, b);
        }

        vertices=newV;
        edges=NormalizeUndirectedEdges(newE);
    }

    void RemoveShortEdges(float minEdgeLength = 1f)
    {
        HashSet<Edge> kept = new HashSet<Edge>();
        int n = vertices.Count;
        int[] degree = new int[n];
        foreach (var e in edges)
        {
            degree[e.a]++;
        }

        int total = Mathf.Max(1, edges.Count);
        int step = Mathf.Max(1, total / 100);
        int processed = 0;
        foreach (var e in edges)
        {
            if (Vector3.Distance(vertices[e.a], vertices[e.b]) >= minEdgeLength || degree[e.a] != 1 || degree[e.b] != 1)
                kept.Add(e);

            processed++;
            if (processed % step == 0 || processed == total)
                LogProgressBar("RemoveShortEdges", processed, total);
        }

        edges = kept;
    }

    void RemoveFloatingNodes()
    {
        int n = vertices.Count;

        int[] degree = new int[n];
        int totalWork = Mathf.Max(1, n + edges.Count * 2);
        int progress = 0;
        int step = Mathf.Max(1, totalWork / 100);
        foreach (var e in edges)
        {
            if (e.a < n && e.b < n)
            {
                degree[e.a]++;
            }
            progress++;
            if (progress % step == 0 || progress == totalWork)
                LogProgressBar("RemoveFloatingNodes", progress, totalWork);
        }

        int[] map = new int[n];
        List<Vector3> newVertices = new List<Vector3>();

        for (int i = 0; i < n; i++)
        {
            if (degree[i] == 0)
            {
                map[i] = -1;
            }
            else
            {
                map[i] = newVertices.Count;
                newVertices.Add(vertices[i]);
            }
            progress++;
            if (progress % step == 0 || progress == totalWork)
                LogProgressBar("RemoveFloatingNodes", progress, totalWork);
        }

        HashSet<Edge> newEdges = new HashSet<Edge>();

        foreach (var e in edges)
        {
            int a = map[e.a];
            int b = map[e.b];

            if (a != -1 && b != -1 && a != b)
            {
                AddUndirectedEdge(newEdges, a, b);
            }
            progress++;
            if (progress % step == 0 || progress == totalWork)
                LogProgressBar("RemoveFloatingNodes", progress, totalWork);
        }

        vertices = newVertices;
        edges = NormalizeUndirectedEdges(newEdges);
    }

    void RemoveEndpoints(float maxEdgeLength = 20f, float rightAngleTolerance = 20f)
    {
        int n = vertices.Count;
        int[] degree = new int[n];
        List<HashSet<int>> adj = new List<HashSet<int>>(n);

        for (int i = 0; i < n; i++)
            adj.Add(new HashSet<int>());

        foreach (var e in edges)
        {
            if (e.a >= 0 && e.a < n && e.b >= 0 && e.b < n)
            {
                if (adj[e.a].Add(e.b))
                    degree[e.a]++;
            }
        }

        int[] map = new int[n];
        List<Vector3> newVertices = new List<Vector3>();
        for (int i = 0; i < n; i++)
        {
            bool remove = false;
            if (degree[i] == 1)
            {
                var it = adj[i].GetEnumerator();
                if (it.MoveNext())
                {
                    int v = it.Current;
                    if ((vertices[i] - vertices[v]).magnitude <= maxEdgeLength)
                    {
                        Vector3 leafDir = (vertices[i] - vertices[v]).normalized;
                        foreach (int nb in adj[v])
                        {
                            if (nb == i) continue;
                            float angle = Vector3.Angle(leafDir, (vertices[nb] - vertices[v]).normalized);
                            if (Mathf.Abs(angle - 90f) <= rightAngleTolerance)
                            {
                                remove = true;
                                break;
                            }
                        }
                    }
                }
            }

            if (remove)
            {
                map[i] = -1;
            }
            else
            {
                map[i] = newVertices.Count;
                newVertices.Add(vertices[i]);
            }
        }

        HashSet<Edge> newEdges = new HashSet<Edge>();
        foreach (var e in edges)
        {
            int a = map[e.a];
            int b = map[e.b];
            if (a != -1 && b != -1 && a != b)
                AddUndirectedEdge(newEdges, a, b);
        }

        vertices = newVertices;
        edges = NormalizeUndirectedEdges(newEdges);
    }

    void DeduplicateEdges()
    {
        edges = NormalizeUndirectedEdges(edges);
    }

    void RemoveCycles(int maxCycleLength = 10)
    {
        int n = vertices.Count;

        List<List<int>> adj = new List<List<int>>();
        for (int i = 0; i < n; i++) adj.Add(new List<int>());

        foreach (var e in edges)
        {
            adj[e.a].Add(e.b);
        }

        HashSet<string> edgesToRemove = new HashSet<string>();
        List<List<int>> cycles = FindCyclesDfs(adj, maxCycleLength);
        int total = Mathf.Max(1, cycles.Count);
        int step = Mathf.Max(1, total / 100);
        for (int i = 0; i < cycles.Count; i++)
        {
            ProcessCycle(cycles[i], adj, edgesToRemove);
            int processed = i + 1;
            if (processed % step == 0 || processed == total)
                LogProgressBar($"RemoveCycles({maxCycleLength})", processed, total);
        }

        edges.RemoveWhere(e =>
        {
            return edgesToRemove.Contains(DirectedEdgeKey(e.a, e.b));
        });
    }

    void ProcessCycle(List<int> cycle,
                  List<List<int>> adj,
                  HashSet<string> edgesToRemove)
    {
        if (cycle == null || cycle.Count < 3) return;

        HashSet<int> set = new HashSet<int>(cycle);

        List<(int a, int b, float w)> edgesInCycle = new List<(int, int, float)>();

        foreach (int a in cycle)
        {
            foreach (int b in adj[a])
            {
                if (!set.Contains(b)) continue;
                if (a < b) // avoid duplicates
                {
                    float w = Vector3.Distance(vertices[a], vertices[b]);
                    edgesInCycle.Add((a, b, w));
                }
            }
        }

        edgesInCycle.Sort((x, y) => x.w.CompareTo(y.w));

        Dictionary<int, int> parent = new Dictionary<int, int>();

        int Find(int x)
        {
            if (parent[x] != x)
                parent[x] = Find(parent[x]);
            return parent[x];
        }

        void Union(int a, int b)
        {
            parent[Find(a)] = Find(b);
        }

        foreach (int v in cycle)
            parent[v] = v;

        HashSet<string> keep = new HashSet<string>();

        foreach (var e in edgesInCycle)
        {
            if (Find(e.a) != Find(e.b))
            {
                Union(e.a, e.b);

                AddUndirectedEdgeKeys(keep, e.a, e.b);
            }
        }

        foreach (var e in edgesInCycle)
        {
            string key = DirectedEdgeKey(e.a, e.b);

            if (!keep.Contains(key))
                AddUndirectedEdgeKeys(edgesToRemove, e.a, e.b);
        }
    }

    string CanonicalCycleKey(List<int> cycle)
    {
        List<int> sorted = new List<int>(cycle);
        sorted.Sort();
        return string.Join(",", sorted);
    }

    List<List<int>> FindCyclesDfs(List<List<int>> adj, int maxCycleLength)
    {
        HashSet<string> seen = new HashSet<string>();
        List<List<int>> cycles = new List<List<int>>();

        for (int start = 0; start < adj.Count; start++)
        {
            bool[] inPath = new bool[adj.Count];
            List<int> path = new List<int> { start };
            inPath[start] = true;
            FindCyclesDfsVisit(start, start, adj, inPath, path, seen, cycles, maxCycleLength);
        }

        return cycles;
    }

    void FindCyclesDfsVisit(int start, int node,
                            List<List<int>> adj,
                            bool[] inPath,
                            List<int> path,
                            HashSet<string> seen,
                            List<List<int>> cycles,
                            int maxCycleLength)
    {
        foreach (int nb in adj[node])
        {
            if (nb < start) continue;

            if (nb == start)
            {
                if (path.Count >= 3)
                {
                    string key = CanonicalCycleKey(path);
                    if (seen.Add(key))
                        cycles.Add(new List<int>(path));
                }
                continue;
            }

            if (path.Count >= maxCycleLength || inPath[nb])
                continue;

            inPath[nb] = true;
            path.Add(nb);
            FindCyclesDfsVisit(start, nb, adj, inPath, path, seen, cycles, maxCycleLength);
            path.RemoveAt(path.Count - 1);
            inPath[nb] = false;
        }
    }
    void Connect(bool connectOne = false, float radius = 0, float angleThreshold = 0, bool specialCase = false)
    {
        
        int n = vertices.Count;

        int[] degree = new int[n];
        foreach (var e in edges)
        {
            degree[e.a]++;
        }

        int total = Mathf.Max(1, n * 3);
        int progress = 0;
        int step = Mathf.Max(1, total / 100);

        if (connectOne)
        {
            Dictionary<Vector2Int, List<int>> spatial = BuildSpatialHash(radius);
            ConnectBreakpoints(degree, radius, angleThreshold, spatial, ref progress, total, step, specialCase);
            return;
        }

        Dictionary<Vector2Int, List<int>> spatial20 = BuildSpatialHash(20f);
        Dictionary<Vector2Int, List<int>> spatial15 = BuildSpatialHash(15f);

        for (int i = 0; i < n; i++)
        {
            if (degree[i] != 0) continue;

            float bestDistSq = float.MaxValue;
            int bestJ = -1;

            foreach (int j in QuerySpatialHash(spatial20, vertices[i], 20f))
            {
                if (i == j) continue;
                if (degree[j] >= 2) continue;

                float distSq = (vertices[i] - vertices[j]).sqrMagnitude;

                if (distSq < bestDistSq)
                {
                    bestDistSq = distSq;
                    bestJ = j;
                }
            }

            if (bestJ != -1)
            {
                AddUndirectedEdge(edges, i, bestJ);
                degree[i]++;
                degree[bestJ]++;
            }

            progress++;
            if (progress % step == 0 || progress == total)
                LogProgressBar("Connect", progress, total);
        }

        ConnectBreakpoints(degree, 20f, 40f, spatial20, ref progress, total, step, specialCase);

        List<List<int>> adj = new List<List<int>>();
        for (int i = 0; i < n; i++)
            adj.Add(new List<int>());

        foreach (var e in edges)
        {
            adj[e.a].Add(e.b);
        }

        for (int i = 0; i < n; i++)
        {
            if (degree[i] == 2)
            {
                int u = adj[i][0];
                int v = adj[i][1];
                if (Vector3.Angle(vertices[u] - vertices[i], vertices[v] - vertices[i]) < 135f)
                {
                    float minDist = 15f;
                    float minDistSq = minDist * minDist;
                    int w = -1;
                    foreach (int j in QuerySpatialHash(spatial15, vertices[i], minDist))
                    {
                        if (j == i || j == u || j == v) continue;
                        float distSq = (vertices[i] - vertices[j]).sqrMagnitude;
                        if ((degree[j] > 2 || (degree[j] == 2 && Vector3.Angle(vertices[adj[j][0]] - vertices[j], vertices[adj[j][1]] - vertices[j]) < 135f)) && distSq < minDistSq)
                        {
                            minDistSq = distSq;
                            w = j;
                        }
                    }
                    if (w == -1)
                    {
                        continue;
                    }
                    if (HasUndirectedEdge(i, w)) continue;
                    AddUndirectedEdge(edges, i, w);
                    degree[i]++;
                    degree[w]++;
                }
            }

            progress++;
            if (progress % step == 0 || progress == total)
                LogProgressBar("Connect", progress, total);
        }
    }

    void ConnectBreakpoints(int[] degree, float radius, float angleThreshold, Dictionary<Vector2Int, List<int>> spatial, ref int progress, int total, int step, bool specialCase)
    {
        int n = vertices.Count;
        List<CandidateEdge> candidates = new List<CandidateEdge>();
        for (int i = 0; i < n; i++)
        {
            if (degree[i] != 1) continue;

            int neighbor = -1;
            foreach (var e in edges)
            {
                if (e.a == i) { neighbor = e.b; break; }
            }

            if (neighbor == -1) continue;

            Vector3 dir0 = (vertices[i] - vertices[neighbor]).normalized;
            float radiusSq = radius * radius;
            foreach (int j in QuerySpatialHash(spatial, vertices[i], radius))
            {
                if (j == i || j == neighbor) continue;
                if (HasUndirectedEdge(i, j)) continue;

                Vector3 delta = vertices[j] - vertices[i];
                float distSq = delta.sqrMagnitude;
                if (distSq > radiusSq) continue;

                Vector3 dir1 = delta.normalized;
                if ((specialCase && Mathf.Abs(Vector3.Angle(dir0, dir1) - 45f) <= angleThreshold) ||
                    (specialCase && degree[j] != 1 && Mathf.Abs(Vector3.Angle(dir0, dir1) - 90f) <= angleThreshold) ||
                    Mathf.Abs(Vector3.Angle(dir0, dir1)) <= angleThreshold)
                    candidates.Add(new CandidateEdge(i, j, Mathf.Sqrt(distSq), 0f));
            }

            progress++;
            if (progress % step == 0 || progress == total)
                LogProgressBar("Connect", progress, total);
        }

        candidates.Sort();
        bool[] vis = new bool[n];
        foreach (var c in candidates)
        {
            if (vis[c.a]) continue;
            if (HasUndirectedEdge(c.a, c.b)) continue;

            AddUndirectedEdge(edges, c.a, c.b);
            degree[c.a]++;
            degree[c.b]++;
            vis[c.a] = true;
        }
    }

    void ConnectDegreeThreeVertices(float maxDistance, float angleThreshold)
    {
        int n = vertices.Count;
        int[] degree = new int[n];
        List<HashSet<int>> adj = new List<HashSet<int>>(n);
        for (int i = 0; i < n; i++)
            adj.Add(new HashSet<int>());

        foreach (var e in edges)
        {
            if (e.a == e.b) continue;
            if (adj[e.a].Add(e.b))
                degree[e.a]++;
        }

        Dictionary<Vector2Int, List<int>> spatial = BuildSpatialHash(maxDistance);
        float maxDistanceSq = maxDistance * maxDistance;
        List<CandidateEdge> candidates = new List<CandidateEdge>();

        for (int u = 0; u < n; u++)
        {
            if (degree[u] != 3 && degree[u] != 2) continue;

            int best = -1;
            float bestDistSq = float.MaxValue;

            foreach (int v in QuerySpatialHash(spatial, vertices[u], maxDistance))
            {
                if (v == u) continue;
                if (degree[v] != 2 && degree[v] != 3) continue;
                if (adj[u].Contains(v)) continue;

                Vector3 delta = vertices[v] - vertices[u];
                float distSq = delta.sqrMagnitude;
                if (distSq > maxDistanceSq || distSq >= bestDistSq) continue;

                Vector3 dir = delta.normalized;
                bool aligned = false;
                foreach (int nb in adj[u])
                {
                    float angle = Vector3.Angle((vertices[nb] - vertices[u]).normalized, dir);
                    if (Mathf.Min(angle, Mathf.Abs(angle - 180f)) <= angleThreshold)
                    {
                        aligned = true;
                        break;
                    }
                }

                if (!aligned) continue;
                best = v;
                bestDistSq = distSq;
            }

            if (best != -1)
                candidates.Add(new CandidateEdge(u, best, Mathf.Sqrt(bestDistSq), 0f));
        }

        candidates.Sort();
        bool[] used = new bool[n];
        foreach (var c in candidates)
        {
            if (used[c.a]) continue;
            if (adj[c.a].Contains(c.b)) continue;

            AddUndirectedEdge(edges, c.a, c.b);
            adj[c.a].Add(c.b);
            adj[c.b].Add(c.a);
            degree[c.a]++;
            degree[c.b]++;
            used[c.a] = true;
        }
    }

    struct CandidateEdge : IComparable<CandidateEdge>
    {
        public int a, b;
        public float dist;
        public float angle;

        public CandidateEdge(int a, int b, float dist, float angle)
        {
            this.a = a;
            this.b = b;
            this.dist = dist;
            this.angle = angle;
        }

        public int CompareTo(CandidateEdge other)
        {
            return dist.CompareTo(other.dist);
        }

    }

    void DeleteOverlapEdges(float angleThreshold = 10f)
    {
        int n = vertices.Count;
        List<HashSet<int>> adj = new List<HashSet<int>>();
        int[] degree = new int[n];

        for (int i = 0; i < n; i++)
            adj.Add(new HashSet<int>());

        foreach (var e in edges)
        {
            if (e.a == e.b) continue;
            if (adj[e.a].Add(e.b))
                degree[e.a]++;
        }

        void Disconnect(int a, int b)
        {
            if (adj[a].Remove(b))
                degree[a]--;
            if (adj[b].Remove(a))
                degree[b]--;
        }

        void ConnectNodes(int a, int b)
        {
            if (a == b) return;
            if (adj[a].Add(b))
                degree[a]++;
            if (adj[b].Add(a))
                degree[b]++;
        }

        int total = Mathf.Max(1, n);
        int step = Mathf.Max(1, total / 100);

        for (int u = 0; u < n; u++)
        {
            bool localChanged = true;

            while (localChanged)
            {
                localChanged = false;
                List<int> neighbors = new List<int>(adj[u]);

                for (int i = 0; i < neighbors.Count && !localChanged; i++)
                {
                    int v = neighbors[i];
                    Vector3 uv = vertices[v] - vertices[u];
                    float distUv = uv.magnitude;
                    if (distUv <= 1e-5f) continue;

                    for (int j = i + 1; j < neighbors.Count; j++)
                    {
                        int w = neighbors[j];
                        Vector3 uw = vertices[w] - vertices[u];
                        float distUw = uw.magnitude;
                        if (distUw <= 1e-5f) continue;

                        float angle = Vector3.Angle(uv, uw);
                        if (angle > angleThreshold) continue;

                        int near = distUv <= distUw ? v : w;
                        int far = distUv <= distUw ? w : v;

                        Disconnect(u, far);
                        ConnectNodes(near, far);
                        localChanged = true;
                        break;
                    }
                }
            }

            int processed = u + 1;
            if (processed % step == 0 || processed == total)
                LogProgressBar("DeleteOverlapEdges", processed, total);
        }

        HashSet<Edge> newEdges = new HashSet<Edge>();
        for (int i = 0; i < n; i++)
        {
            foreach (int j in adj[i])
            {
                AddUndirectedEdge(newEdges, i, j);
            }
        }

        edges = NormalizeUndirectedEdges(newEdges);
    }

    void FinalCluster(float clusterRadius, bool lastStep = false, float rightAngleError = 45f)
    {
        int n = vertices.Count;
        List<HashSet<int>> adj = new List<HashSet<int>>(n);
        List<int> degree = new List<int>(new int[n]);
        HashSet<int> removed = new HashSet<int>();

        for (int i = 0; i < n; i++)
            adj.Add(new HashSet<int>());

        foreach (var e in edges)
        {
            if (e.a == e.b) continue;
            if (adj[e.a].Add(e.b)) degree[e.a]++;
        }

        void Disconnect(int a, int b)
        {
            if (adj[a].Remove(b)) degree[a]--;
            if (adj[b].Remove(a)) degree[b]--;
        }

        void ConnectNodes(int a, int b)
        {
            if (a == b) return;
            if (adj[a].Add(b)) degree[a]++;
            if (adj[b].Add(a)) degree[b]++;
        }

        float GetInternalRightAngleError(int v)
        {
            float bestError = float.MaxValue;
            foreach (int nb1 in adj[v])
            {
                Vector3 d1 = (vertices[nb1] - vertices[v]).normalized;
                foreach (int nb2 in adj[v])
                {
                    if (nb1 == nb2) continue;
                    Vector3 d2 = (vertices[nb2] - vertices[v]).normalized;
                    float angle = Vector3.Angle(d1, d2);
                    bestError = Mathf.Min(bestError, Mathf.Abs(angle - 90f));
                }
            }

            return bestError;
        }

        bool isCrossroad(int v)
        {
            if (degree[v] == 3)
            {
                var it = adj[v].GetEnumerator();
                it.MoveNext(); var a = it.Current;
                it.MoveNext(); var b = it.Current;
                it.MoveNext(); var c = it.Current;
                Vector3 d1 = (vertices[a] - vertices[v]).normalized;
                Vector3 d2 = (vertices[b] - vertices[v]).normalized;
                Vector3 d3 = (vertices[c] - vertices[v]).normalized;
                float angle1 = Vector3.Angle(d1, d2);
                float angle2 = Vector3.Angle(d2, d3);
                float angle3 = Vector3.Angle(d3, d1);
                return Mathf.Abs(angle1 - 180f) <= 15f || Mathf.Abs(angle2 - 180f) <= 15f || Mathf.Abs(angle3 - 180f) <= 15f;
            }
            return degree[v] == 4;
        }

        bool OtherNeighborsAreRightAngle(int a, int b)
        {
            List<int> others = new List<int>();
            foreach (int nb in adj[a])
                if (nb != b)
                    others.Add(nb);

            if (others.Count != 2) return false;

            Vector3 d0 = (vertices[others[0]] - vertices[a]).normalized;
            Vector3 d1 = (vertices[others[1]] - vertices[a]).normalized;
            return Mathf.Abs(Vector3.Angle(d0, d1) - 90f) <= 30f;
        }

        bool IsSpecialPair(int a, int b)
        {
            return
                degree[a] == 3 &&
                degree[b] == 3 &&
                adj[a].Contains(b) &&
                OtherNeighborsAreRightAngle(a, b) &&
                OtherNeighborsAreRightAngle(b, a);
        }

        List<(int center, List<int> nodes, float radius)> candidates = new List<(int, List<int>, float)>();
        for (int u = 0; u < n; u++)
        {
            List<int> cluster = new List<int> { u };
            Vector3 centroid = vertices[u];
            Vector3 sum = vertices[u];
            float radius = 0f;

            while (true)
            {
                HashSet<int> nearby = new HashSet<int>();
                foreach (int start in cluster)
                {
                    Queue<(int node, int depth)> q = new Queue<(int, int)>();
                    HashSet<int> seen = new HashSet<int> { start };
                    q.Enqueue((start, 0));

                    while (q.Count > 0)
                    {
                        var item = q.Dequeue();
                        int a = item.node;
                        int depth = item.depth;
                        if (depth == 5) continue;

                        foreach (int b in adj[a])
                        {
                            if (!seen.Add(b) || Vector3.Distance(centroid, vertices[b]) > clusterRadius) continue;
                            nearby.Add(b);
                            q.Enqueue((b, depth + 1));
                        }
                    }
                }

                nearby.RemoveWhere(cluster.Contains);
                if (nearby.Count == 0) break;

                List<int> nextCandidates = new List<int>(nearby);
                nextCandidates.Sort((a, b) =>
                    Vector3.Distance(centroid, vertices[a]).CompareTo(
                    Vector3.Distance(centroid, vertices[b])));

                int accepted = -1;
                float acceptedDist = 0f;
                foreach (int v in nextCandidates)
                {
                    float dist = Vector3.Distance(centroid, vertices[v]);
                    if (dist > clusterRadius) break;
                    accepted = v;
                    acceptedDist = dist;
                    break;
                }

                if (accepted == -1) break;

                cluster.Add(accepted);
                sum += vertices[accepted];
                centroid = sum / cluster.Count;
                radius = Mathf.Max(radius, acceptedDist);
            }

            if (cluster.Count >= 2)
                candidates.Add((u, cluster, radius));
        }

        candidates.Sort((a, b) => a.radius.CompareTo(b.radius));
        int total = Mathf.Max(1, candidates.Count);
        int step = Mathf.Max(1, total / 100);

        for (int i = 0; i < candidates.Count; i++)
        {
            int u = candidates[i].center;
            if (removed.Contains(u))
            {
                int processedSkip = i + 1;
                if (processedSkip % step == 0 || processedSkip == total)
                    LogProgressBar("FinalCluster", processedSkip, total);
                continue;
            }

            List<int> cluster = new List<int>();
            foreach (int v in candidates[i].nodes)
            {
                if (removed.Contains(v)) continue;
                if (clusterRadius > 10f && !lastStep)
                {
                    if (isCrossroad(v))
                    {
                        int processedSkip = i + 1;
                        if (processedSkip % step == 0 || processedSkip == total)
                            LogProgressBar("FinalCluster", processedSkip, total);
                        continue;
                    }
                }

                cluster.Add(v);
            }

            if (lastStep)
            {
                int pairA = -1, pairB = -1;
                for (int a = 0; a < cluster.Count; a++)
                {
                    for (int b = a + 1; b < cluster.Count; b++)
                    {
                        if (IsSpecialPair(cluster[a], cluster[b]))
                        {
                            pairA = cluster[a];
                            pairB = cluster[b];
                            break;
                        }
                    }
                }

                if (pairA != -1)
                    cluster = new List<int> { pairA, pairB };
                else
                {
                    int processedSkip = i + 1;
                    if (processedSkip % step == 0 || processedSkip == total)
                        LogProgressBar("FinalCluster", processedSkip, total);
                    continue;
                }
            }

            if (cluster.Count < 2)
            {
                int processedSkip = i + 1;
                if (processedSkip % step == 0 || processedSkip == total)
                    LogProgressBar("FinalCluster", processedSkip, total);
                continue;
            }

            HashSet<int> clusterSet = new HashSet<int>(cluster);
            HashSet<int> external = new HashSet<int>();
            foreach (int a in cluster)
                foreach (int b in adj[a])
                    if (!clusterSet.Contains(b) && !removed.Contains(b))
                        external.Add(b);

            List<(int v, float error)> rightAngles = new List<(int, float)>();
            foreach (int v in cluster)
            {
                float error = GetInternalRightAngleError(v);
                if (error <= rightAngleError || degree[v] == 4)
                    rightAngles.Add((v, error));
            }

            List<Vector3> reps = new List<Vector3>();
            bool forceSingleCentroid = clusterRadius <= 10f || (lastStep && cluster.Count == 2 && IsSpecialPair(cluster[0], cluster[1]));

            if (!forceSingleCentroid && rightAngles.Count > 0)
            {
                rightAngles.Sort((a, b) => a.error.CompareTo(b.error));
                int best0 = rightAngles[0].v;
                reps.Add(vertices[best0]);
                if (rightAngles.Count > 1)
                {
                    int best1 = rightAngles[1].v;
                    float bestDistSq = (vertices[best0] - vertices[best1]).sqrMagnitude;
                    for (int k = 1; k < rightAngles.Count; k++)
                    {
                        float distSq = (vertices[best0] - vertices[rightAngles[k].v]).sqrMagnitude;
                        if (distSq > bestDistSq)
                        {
                            bestDistSq = distSq;
                            best1 = rightAngles[k].v;
                        }
                    }
                    reps.Add(vertices[best1]);
                }
            }
            else
            {
                Vector3 centroid = Vector3.zero;
                foreach (int a in cluster)
                    centroid += vertices[a];
                reps.Add(centroid / cluster.Count);
            }

            foreach (int a in cluster)
            {
                foreach (int b in new List<int>(adj[a]))
                    Disconnect(a, b);
                removed.Add(a);
            }

            int firstRep = vertices.Count;
            foreach (var rep in reps)
            {
                vertices.Add(rep);
                adj.Add(new HashSet<int>());
                degree.Add(0);
            }

            if (reps.Count == 2)
                ConnectNodes(firstRep, firstRep + 1);

            foreach (int b in external)
            {
                int target = firstRep;
                if (reps.Count == 2 &&
                    (vertices[b] - reps[1]).sqrMagnitude < (vertices[b] - reps[0]).sqrMagnitude)
                    target = firstRep + 1;
                ConnectNodes(target, b);
            }

            int processed = i + 1;
            if (processed % step == 0 || processed == total)
                LogProgressBar("FinalCluster", processed, total);
        }

        int[] map = new int[vertices.Count];
        List<Vector3> newVertices = new List<Vector3>();
        for (int i = 0; i < vertices.Count; i++)
        {
            if (removed.Contains(i)) map[i] = -1;
            else
            {
                map[i] = newVertices.Count;
                newVertices.Add(vertices[i]);
            }
        }

        HashSet<Edge> newEdges = new HashSet<Edge>();
        for (int i = 0; i < adj.Count; i++)
        {
            if (removed.Contains(i)) continue;
            foreach (int j in adj[i])
            {
                if (removed.Contains(j)) continue;
                AddUndirectedEdge(newEdges, map[i], map[j]);
            }
        }

        vertices = newVertices;
        edges = NormalizeUndirectedEdges(newEdges);
    }

    void SpecialProcess(float clusterRadius)
    {
        int n = vertices.Count;
        List<HashSet<int>> adj = new List<HashSet<int>>(n);
        HashSet<int> removed = new HashSet<int>();
        List<(Vector3 centroid, HashSet<int> external)> centroidAdds = new List<(Vector3, HashSet<int>)>();

        for (int i = 0; i < n; i++)
            adj.Add(new HashSet<int>());

        foreach (var e in edges)
        {
            if (e.a != e.b)
                adj[e.a].Add(e.b);
        }

        void Disconnect(int a, int b)
        {
            adj[a].Remove(b);
            adj[b].Remove(a);
        }

        List<(int center, List<int> nodes, float radius)> candidates = new List<(int, List<int>, float)>();
        for (int u = 0; u < n; u++)
        {
            List<int> cluster = new List<int> { u };
            Vector3 centroid = vertices[u];
            Vector3 sum = vertices[u];
            float radius = 0f;

            while (true)
            {
                HashSet<int> nearby = new HashSet<int>();
                foreach (int start in cluster)
                {
                    Queue<(int node, int depth)> q = new Queue<(int, int)>();
                    HashSet<int> seen = new HashSet<int> { start };
                    q.Enqueue((start, 0));

                    while (q.Count > 0)
                    {
                        var item = q.Dequeue();
                        if (item.depth == 5) continue;

                        foreach (int b in adj[item.node])
                        {
                            if (!seen.Add(b)) continue;
                            nearby.Add(b);
                            q.Enqueue((b, item.depth + 1));
                        }
                    }
                }

                nearby.RemoveWhere(cluster.Contains);
                if (nearby.Count == 0) break;

                List<int> nextCandidates = new List<int>(nearby);
                nextCandidates.Sort((a, b) =>
                    Vector3.Distance(centroid, vertices[a]).CompareTo(
                    Vector3.Distance(centroid, vertices[b])));

                int accepted = -1;
                float acceptedDist = 0f;
                foreach (int v in nextCandidates)
                {
                    float dist = Vector3.Distance(centroid, vertices[v]);
                    if (dist > clusterRadius) break;
                    accepted = v;
                    acceptedDist = dist;
                    break;
                }

                if (accepted == -1) break;

                cluster.Add(accepted);
                sum += vertices[accepted];
                centroid = sum / cluster.Count;
                radius = Mathf.Max(radius, acceptedDist);
            }

            if (cluster.Count >= 2)
                candidates.Add((u, cluster, radius));
        }

        candidates.Sort((a, b) => a.radius.CompareTo(b.radius));
        int total = Mathf.Max(1, candidates.Count);
        int step = Mathf.Max(1, total / 100);

        for (int i = 0; i < candidates.Count; i++)
        {
            int u = candidates[i].center;
            if (removed.Contains(u))
            {
                int processedSkip = i + 1;
                if (processedSkip % step == 0 || processedSkip == total)
                    LogProgressBar("FinalCluster", processedSkip, total);
                continue;
            }

            List<int> cluster = new List<int>();
            foreach (int v in candidates[i].nodes)
                if (!removed.Contains(v))
                    cluster.Add(v);

            if (cluster.Count < 2)
            {
                int processedSkip = i + 1;
                if (processedSkip % step == 0 || processedSkip == total)
                    LogProgressBar("FinalCluster", processedSkip, total);
                continue;
            }
            
            HashSet<int> clusterSet = new HashSet<int>(cluster);
            List<int> kept = new List<int>();
            foreach (int v in cluster)
            {
                foreach (int nb in adj[v])
                {
                    if (!clusterSet.Contains(nb) && !removed.Contains(nb))
                    {
                        kept.Add(v);
                        break;
                    }
                }
            }

            if (kept.Count < 2)
            {
                int processedSkip = i + 1;
                if (processedSkip % step == 0 || processedSkip == total)
                    LogProgressBar("FinalCluster", processedSkip, total);
                continue;
            }

            HashSet<int> keepSet = new HashSet<int>(kept);
            foreach (int v in cluster)
            {
                if (keepSet.Contains(v)) continue;
                foreach (int nb in new List<int>(adj[v]))
                    Disconnect(v, nb);
                removed.Add(v);
            }
            
            int processed = i + 1;
            if (processed % step == 0 || processed == total)
                LogProgressBar("FinalCluster", processed, total);
        }

        int[] map = new int[n];
        List<Vector3> newVertices = new List<Vector3>();
        for (int i = 0; i < n; i++)
        {
            if (removed.Contains(i)) map[i] = -1;
            else
            {
                map[i] = newVertices.Count;
                newVertices.Add(vertices[i]);
            }
        }

        foreach (var add in centroidAdds)
        {
            int c = newVertices.Count;
            newVertices.Add(add.centroid);
            adj.Add(new HashSet<int>());
            foreach (int nb in add.external)
            {
                int mapped = map[nb];
                if (mapped == -1) continue;
                adj[c].Add(mapped);
            }
        }

        HashSet<Edge> newEdges = new HashSet<Edge>();
        for (int i = 0; i < adj.Count; i++)
        {
            if (i < n && removed.Contains(i)) continue;
            foreach (int j in adj[i])
            {
                if (j < n && removed.Contains(j)) continue;

                int a = i < n ? map[i] : i;
                int b = j < n ? map[j] : j;
                if (a != -1 && b != -1)
                    AddUndirectedEdge(newEdges, a, b);
            }
        }

        vertices = newVertices;
        edges = NormalizeUndirectedEdges(newEdges);
    }

    void RemoveStraightVertices(float angleThreshold = 165f, float maxEdgeLength = 10f)
    {
        int n = vertices.Count;

        List<HashSet<int>> adj = new List<HashSet<int>>();
        int[] degree = new int[n];

        for (int i = 0; i < n; i++)
            adj.Add(new HashSet<int>());

        foreach (var e in edges)
        {
            adj[e.a].Add(e.b);
            degree[e.a]++;
        }

        Queue<int> q = new Queue<int>();

        for (int i = 0; i < n; i++)
            if (degree[i] == 2)
                q.Enqueue(i);

        bool[] removed = new bool[n];
        int total = Mathf.Max(1, q.Count);
        int processed = 0;
        int step = Mathf.Max(1, total / 100);

        while (q.Count > 0)
        {
            int u = q.Dequeue();
            processed++;

            if (removed[u] || degree[u] != 2) continue;

            var it = adj[u].GetEnumerator();
            it.MoveNext();
            int v = it.Current;
            it.MoveNext();
            int w = it.Current;

            if ((vertices[v] - vertices[u]).magnitude > maxEdgeLength ||
                (vertices[w] - vertices[u]).magnitude > maxEdgeLength)
                continue;

            Vector3 d1 = (vertices[v] - vertices[u]).normalized;
            Vector3 d2 = (vertices[w] - vertices[u]).normalized;

            float angle = Vector3.Angle(d1, d2);

            if (angle <= angleThreshold) continue;
            removed[u] = true;

            adj[v].Remove(u);
            adj[w].Remove(u);

            degree[v]--;
            degree[w]--;

            if (v != w && !adj[v].Contains(w))
            {
                adj[v].Add(w);
                adj[w].Add(v);

                degree[v]++;
                degree[w]++;
            }

            if (degree[v] == 2) q.Enqueue(v);
            if (degree[w] == 2) q.Enqueue(w);

            if (processed % step == 0 || processed == total)
                LogProgressBar("RemoveStraightVertices", processed, total);
        }

        LogProgressBar("RemoveStraightVertices", total, total);

        int[] map = new int[n];
        List<Vector3> newVertices = new List<Vector3>();

        for (int i = 0; i < n; i++)
        {
            if (removed[i]) map[i] = -1;
            else
            {
                map[i] = newVertices.Count;
                newVertices.Add(vertices[i]);
            }
        }

        HashSet<Edge> newEdges = new HashSet<Edge>();

        for (int i = 0; i < n; i++)
        {
            if (removed[i]) continue;

            foreach (int j in adj[i])
            {
                if (!removed[j])
                {
                    int a = map[i];
                    int b = map[j];

                    if (a != b)
                        AddUndirectedEdge(newEdges, a, b);
                }
            }
        }

        vertices = newVertices;
        edges = NormalizeUndirectedEdges(newEdges);
    }

    // ================= EXPORT =================
    void ExportJson()
    {
        string folder = Application.persistentDataPath;
        if (!Directory.Exists(folder)) Directory.CreateDirectory(folder);
        string path = Path.Combine(folder, "road_graph.json");

        using(StreamWriter sw=new StreamWriter(path))
        {
            sw.Write("{\"vertices\":[");
            for(int i=0;i<vertices.Count;i++)
            {
                var v=vertices[i];
                sw.Write($"{{\"id\":{i},\"x\":{v.x},\"y\":{v.y},\"z\":{v.z}}}");
                if(i<vertices.Count-1) sw.Write(",");
            }
            sw.Write("],\"edges\":[");

            int edgeIndex = 0;
            foreach (var e in edges)
            {
                sw.Write($"{{\"from\":{e.a},\"to\":{e.b}}}");
                if(edgeIndex < edges.Count-1) sw.Write(",");
                edgeIndex++;
            }

            sw.Write("]}");
        }
    }

    void OnDrawGizmos()
    {
        if (TryGetGraphBounds(out Bounds graphBounds))
        {
            Gizmos.color = areaGizmoColor;
            Matrix4x4 previous = Gizmos.matrix;
            Gizmos.matrix = Matrix4x4.TRS(
                selectionCenter,
                selectionRotation,
                Vector3.one
            );
            Gizmos.DrawWireCube(Vector3.zero, new Vector3(selectionHalfSize.x * 2f, 0.1f, selectionHalfSize.y * 2f));
            Gizmos.matrix = previous;
        }

        if (!drawGraphGizmos || vertices == null || edges == null) return;

        Gizmos.color = vertexGizmoColor;
        foreach (var v in vertices)
            Gizmos.DrawSphere(v, vertexGizmoRadius);

        Gizmos.color = edgeGizmoColor;
        foreach (var e in edges)
        {
            if (e.a < 0 || e.b < 0 || e.a >= vertices.Count || e.b >= vertices.Count) continue;
            Gizmos.DrawLine(vertices[e.a], vertices[e.b]);
        }
    }
}
