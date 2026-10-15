using System;
using System.IO;
using System.Linq;
using System.Text;
using System.Threading.Tasks;
using Windows.Graphics.Imaging;
using Windows.Media.Ocr;
using Windows.Storage;
using Windows.Storage.Streams;
using System.Runtime.InteropServices.WindowsRuntime;

class OcrTiles
{
    static int Main(string[] args)
    {
        string dir = args.Length > 0 ? args[0] : @"C:\tmp\ocrtiles";
        var engine = OcrEngine.TryCreateFromUserProfileLanguages();
        if (engine == null) { Console.Error.WriteLine("no engine"); return 1; }
        var sb = new StringBuilder("[");
        bool first = true;
        var files = Directory.GetFiles(dir, "t*.jpg").OrderBy(f => f).ToArray();
        foreach (var f in files)
        {
            string tile = Path.GetFileNameWithoutExtension(f);
            string meta = File.ReadAllText(Path.Combine(dir, tile + ".meta")).Trim();
            var mp = meta.Split(',');
            double cx = double.Parse(mp[0]), cy = double.Parse(mp[1]), sc = double.Parse(mp[2]);
            var bmp = DecodeAsync(f).GetAwaiter().GetResult();
            var res = engine.RecognizeAsync(bmp).AsTask().GetAwaiter().GetResult();
            foreach (var line in res.Lines)
            {
                foreach (var w in line.Words)
                {
                    var r = w.BoundingRect;
                    double x = cx + (r.X + r.Width / 2) / sc;
                    double y = cy + (r.Y + r.Height / 2) / sc;
                    double ww = r.Width / sc, hh = r.Height / sc;
                    if (!first) sb.Append(",");
                    first = false;
                    sb.Append("{\"t\":\"").Append(w.Text.Replace("\\", "\\\\").Replace("\"", "\\\"")).Append("\",\"x\":").Append(x.ToString("0.0")).Append(",\"y\":").Append(y.ToString("0.0")).Append(",\"w\":").Append(ww.ToString("0.0")).Append(",\"h\":").Append(hh.ToString("0.0")).Append("}");
                }
            }
        }
        sb.Append("]");
        File.WriteAllText(Path.Combine(dir, "words.json"), sb.ToString(), new UTF8Encoding(false));
        Console.WriteLine("done");
        return 0;
    }

    static Task<SoftwareBitmap> DecodeAsync(string path)
    {
        var file = StorageFile.GetFileFromPathAsync(path).AsTask().GetAwaiter().GetResult();
        using (IRandomAccessStream stream = file.OpenAsync(FileAccessMode.Read).AsTask().GetAwaiter().GetResult())
        {
            var decoder = BitmapDecoder.CreateAsync(stream).AsTask().GetAwaiter().GetResult();
            return decoder.GetSoftwareBitmapAsync().AsTask().GetAwaiter().GetResult();
        }
    }
}
