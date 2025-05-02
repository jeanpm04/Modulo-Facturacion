package SQL;

import java.sql.Connection;
import java.sql.DriverManager;

public class connect {
    public static void main(String[] args) {
        connect();
    }

    public static void connect() {
        Connection conn = null;
        String driver = "com.mysql.cj.jdbc.Driver";
        try {
            Class.forName(driver);
            System.out.println("Driver cargado con éxito.");

            try {
                conn = DriverManager.getConnection(
                    "jdbc:mysql://localhost:3306/facturacion_db?useUnicode=true&useJDBCCompliantTimezoneShift=true&useLegacyDatetimeCode=false&serverTimezone=UTC",
                    "root", "root"
                );
                if (conn != null) {
                    System.out.println("Conexión realizada con éxito.");
                }
            } catch (Exception e) {
                System.out.println("Ha ocurrido un error al intentar conectar con la base de datos: " + e.getMessage());
            }
        } catch (Exception e) {
            System.out.println("Ha ocurrido un error al cargar el driver: " + e.getMessage());
        }
    }
}