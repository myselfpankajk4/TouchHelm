using System;
using System.Collections.Generic;
using System.Runtime.InteropServices;
using System.Runtime.InteropServices.ComTypes;

public static class TouchHelmCameras {
    [ComImport,Guid("29840822-5B84-11D0-BD3B-00A0C911CE86"),InterfaceType(ComInterfaceType.InterfaceIsIUnknown)]
    interface ICreateDevEnum { [PreserveSig]int CreateClassEnumerator(ref Guid category,out IEnumMoniker value,int flags); }
    [ComImport,Guid("55272A00-42CB-11CE-8135-00AA004BB851"),InterfaceType(ComInterfaceType.InterfaceIsIUnknown)]
    interface IPropertyBag {
        [PreserveSig]int Read([MarshalAs(UnmanagedType.LPWStr)]string name,[MarshalAs(UnmanagedType.Struct)]out object value,IntPtr error);
        [PreserveSig]int Write([MarshalAs(UnmanagedType.LPWStr)]string name,[In,MarshalAs(UnmanagedType.Struct)]ref object value);
    }
    public static List<Dictionary<string,object>> List() {
        var result=new List<Dictionary<string,object>>();object device=null;IEnumMoniker enumerator=null;
        try {
            device=Activator.CreateInstance(Type.GetTypeFromCLSID(new Guid("62BE5D10-60EB-11D0-BD3B-00A0C911CE86")));
            var category=new Guid("860BB310-5D01-11D0-BD3B-00A0C911CE86");
            if(((ICreateDevEnum)device).CreateClassEnumerator(ref category,out enumerator,0)!=0)return result;
            var monikers=new IMoniker[1];int index=0;
            while(enumerator.Next(1,monikers,IntPtr.Zero)==0 && index<32) {
                object bag=null;
                try {
                    var iid=new Guid("55272A00-42CB-11CE-8135-00AA004BB851");monikers[0].BindToStorage(null,null,ref iid,out bag);
                    object name;((IPropertyBag)bag).Read("FriendlyName",out name,IntPtr.Zero);
                    result.Add(new Dictionary<string,object>{{"id",index.ToString()},{"name",name as string ?? "Camera "+index}});
                } finally {if(bag!=null)Marshal.ReleaseComObject(bag);Marshal.ReleaseComObject(monikers[0]);}
                index++;
            }
        } finally {if(enumerator!=null)Marshal.ReleaseComObject(enumerator);if(device!=null)Marshal.ReleaseComObject(device);}
        return result;
    }
}
