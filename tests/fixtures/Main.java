import java.io.BufferedInputStream;
import java.io.IOException;
import java.util.StringJoiner;

public class Main {
    private static int n;
    private static int m;
    private static boolean[] used;
    private static int[] selected;
    private static final StringBuilder output = new StringBuilder();

    public static void main(String[] args) throws Exception {
        FastScanner scanner = new FastScanner();
        n = scanner.nextInt();
        m = scanner.nextInt();
        used = new boolean[n + 1];
        selected = new int[m];
        permutation(0);
        System.out.print(output);
    }

    private static void permutation(int depth) {
        if (depth == m) {
            StringJoiner joiner = new StringJoiner(" ");
            for (int value : selected) {
                joiner.add(Integer.toString(value));
            }
            output.append(joiner).append('\n');
            return;
        }
        for (int value = 1; value <= n; value++) {
            if (used[value]) {
                continue;
            }
            used[value] = true;
            selected[depth] = value;
            permutation(depth + 1);
            used[value] = false;
        }
    }

    private static class FastScanner {
        private final BufferedInputStream input = new BufferedInputStream(System.in);
        private final byte[] buffer = new byte[1 << 16];
        private int index = 0;
        private int size = 0;

        private int read() throws IOException {
            if (index >= size) {
                size = input.read(buffer);
                index = 0;
                if (size <= 0) {
                    return -1;
                }
            }
            return buffer[index++];
        }

        int nextInt() throws IOException {
            int c;
            do {
                c = read();
            } while (c <= ' ' && c != -1);

            int sign = 1;
            if (c == '-') {
                sign = -1;
                c = read();
            }

            int value = 0;
            while (c > ' ') {
                value = value * 10 + (c - '0');
                c = read();
            }
            return value * sign;
        }
    }
}
